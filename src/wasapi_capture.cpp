#define WASAPI_CAPTURE_EXPORTS
#include "../include/wasapi_capture.h"

#include <windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <functiondiscoverykeys_devpkey.h>

#include <cmath>
#include <vector>
#include <string>
#include <mutex>
#include <thread>
#include <atomic>
#include <cstring>
#include <cwchar>

#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "mmdevapi.lib")

// 内部捕获会话对象
class WasapiSession {
public:
    WasapiSession(const std::wstring& dev_id, bool loopback, int target_sr, float window_sec)
        : device_id(dev_id),
          is_loopback(loopback),
          target_sample_rate(target_sr),
          window_seconds(window_sec),
          running(false),
          current_level(0.0f),
          total_samples(0),
          resample_phase(0.0),
          last_input_sample(0.0f)
    {
        ring_capacity = (size_t)(target_sample_rate * (window_seconds > 1.0f ? window_seconds : 30.0f));
        if (ring_capacity < 16000) ring_capacity = 16000;
        ring_buffer.resize(ring_capacity, 0.0f);
        ring_write_pos = 0;
        ring_count = 0;
    }

    ~WasapiSession() {
        stop();
    }

    bool start() {
        if (running.load()) return true;
        running.store(true);
        capture_thread = std::thread(&WasapiSession::thread_loop, this);
        return true;
    }

    void stop() {
        if (running.load()) {
            running.store(false);
            if (capture_thread.joinable()) {
                capture_thread.join();
            }
        }
    }

    bool is_active() const {
        return running.load();
    }

    float get_level() const {
        return current_level.load();
    }

    long long get_total() const {
        std::lock_guard<std::mutex> lock(buf_mutex);
        return total_samples;
    }

    int snapshot(float seconds, float* out_buf, int max_samples, double* out_start_sec) {
        if (!out_buf || max_samples <= 0) return 0;
        std::lock_guard<std::mutex> lock(buf_mutex);

        size_t req_samples = (size_t)(seconds * target_sample_rate);
        if (req_samples > (size_t)max_samples) req_samples = (size_t)max_samples;
        if (req_samples > ring_count) req_samples = ring_count;

        if (req_samples == 0) {
            if (out_start_sec) *out_start_sec = 0.0;
            return 0;
        }

        // 从环形缓冲的尾部取出最近 req_samples 个样本
        size_t start_pos = (ring_write_pos + ring_capacity - req_samples) % ring_capacity;
        for (size_t i = 0; i < req_samples; ++i) {
            out_buf[i] = ring_buffer[(start_pos + i) % ring_capacity];
        }

        if (out_start_sec) {
            long long sample_start = total_samples - (long long)req_samples;
            if (sample_start < 0) sample_start = 0;
            *out_start_sec = (double)sample_start / (double)target_sample_rate;
        }
        return (int)req_samples;
    }

    int read_samples(float* out_buf, int max_samples) {
        if (!out_buf || max_samples <= 0) return 0;
        std::lock_guard<std::mutex> lock(buf_mutex);

        size_t to_read = (size_t)max_samples;
        if (to_read > unread_count) to_read = unread_count;
        if (to_read == 0) return 0;

        size_t start_pos = (ring_write_pos + ring_capacity - unread_count) % ring_capacity;
        for (size_t i = 0; i < to_read; ++i) {
            out_buf[i] = ring_buffer[(start_pos + i) % ring_capacity];
        }
        unread_count -= to_read;
        return (int)to_read;
    }

    std::string get_last_error() {
        std::lock_guard<std::mutex> lock(err_mutex);
        return last_error;
    }

    void set_error(const std::string& err) {
        std::lock_guard<std::mutex> lock(err_mutex);
        last_error = err;
    }

private:
    void thread_loop() {
        HRESULT hr = CoInitializeEx(NULL, COINIT_MULTITHREADED);
        bool co_inited = SUCCEEDED(hr);

        IMMDeviceEnumerator* pEnumerator = NULL;
        IMMDevice* pDevice = NULL;
        IAudioClient* pAudioClient = NULL;
        IAudioCaptureClient* pCaptureClient = NULL;
        WAVEFORMATEX* pwfx = NULL;

        hr = CoCreateInstance(__uuidof(MMDeviceEnumerator), NULL, CLSCTX_ALL,
                              __uuidof(IMMDeviceEnumerator), (void**)&pEnumerator);
        if (FAILED(hr)) {
            set_error("CoCreateInstance MMDeviceEnumerator failed");
            goto cleanup;
        }

        if (device_id.empty()) {
            EDataFlow flow = is_loopback ? eRender : eCapture;
            hr = pEnumerator->GetDefaultAudioEndpoint(flow, eConsole, &pDevice);
        } else {
            hr = pEnumerator->GetDevice(device_id.c_str(), &pDevice);
        }

        if (FAILED(hr) || !pDevice) {
            set_error("Failed to get audio device endpoint");
            goto cleanup;
        }

        hr = pDevice->Activate(__uuidof(IAudioClient), CLSCTX_ALL, NULL, (void**)&pAudioClient);
        if (FAILED(hr) || !pAudioClient) {
            set_error("Failed to activate IAudioClient");
            goto cleanup;
        }

        hr = pAudioClient->GetMixFormat(&pwfx);
        if (FAILED(hr) || !pwfx) {
            set_error("Failed to get device mix format");
            goto cleanup;
        }

        // 申请 1 秒的缓冲区大小 (10000000 相当于 1 秒，以 100ns 为单位)
        REFERENCE_TIME hnsRequestedDuration = 10000000;
        DWORD streamFlags = is_loopback ? AUDCLNT_STREAMFLAGS_LOOPBACK : 0;

        hr = pAudioClient->Initialize(AUDCLNT_SHAREMODE_SHARED,
                                      streamFlags,
                                      hnsRequestedDuration,
                                      0,
                                      pwfx,
                                      NULL);
        if (FAILED(hr)) {
            set_error("IAudioClient::Initialize failed");
            goto cleanup;
        }

        hr = pAudioClient->GetService(__uuidof(IAudioCaptureClient), (void**)&pCaptureClient);
        if (FAILED(hr) || !pCaptureClient) {
            set_error("Failed to get IAudioCaptureClient service");
            goto cleanup;
        }

        hr = pAudioClient->Start();
        if (FAILED(hr)) {
            set_error("IAudioClient::Start failed");
            goto cleanup;
        }

        // 捕获循环
        while (running.load()) {
            Sleep(15);

            UINT32 packetLength = 0;
            hr = pCaptureClient->GetNextPacketSize(&packetLength);
            if (FAILED(hr)) break;

            while (packetLength > 0) {
                BYTE* pData = NULL;
                UINT32 numFramesAvailable = 0;
                DWORD flags = 0;

                hr = pCaptureClient->GetBuffer(&pData, &numFramesAvailable, &flags, NULL, NULL);
                if (FAILED(hr)) break;

                process_audio_packet(pData, numFramesAvailable, flags, pwfx);

                pCaptureClient->ReleaseBuffer(numFramesAvailable);

                hr = pCaptureClient->GetNextPacketSize(&packetLength);
                if (FAILED(hr)) break;
            }
        }

        pAudioClient->Stop();

cleanup:
        if (pwfx) CoTaskMemFree(pwfx);
        if (pCaptureClient) pCaptureClient->Release();
        if (pAudioClient) pAudioClient->Release();
        if (pDevice) pDevice->Release();
        if (pEnumerator) pEnumerator->Release();
        if (co_inited) CoUninitialize();
    }

    void process_audio_packet(BYTE* pData, UINT32 numFrames, DWORD flags, const WAVEFORMATEX* pwfx) {
        if (numFrames == 0) return;

        bool is_silent = (flags & AUDCLNT_BUFFERFLAGS_SILENT) != 0;
        int channels = pwfx->nChannels;
        int src_sample_rate = (int)pwfx->nSamplesPerSec;

        // 1. 将音频帧解析混音为单声道 float32
        std::vector<float> mono_samples(numFrames, 0.0f);
        if (!is_silent && pData != NULL) {
            bool is_float = (pwfx->wFormatTag == WAVE_FORMAT_IEEE_FLOAT);
            if (pwfx->wFormatTag == WAVE_FORMAT_EXTENSIBLE) {
                const WAVEFORMATEXTENSIBLE* pExt = (const WAVEFORMATEXTENSIBLE*)pwfx;
                if (pExt->SubFormat == KSDATAFORMAT_SUBTYPE_IEEE_FLOAT) {
                    is_float = true;
                }
            }

            int bytes_per_sample = pwfx->wBitsPerSample / 8;
            if (is_float && bytes_per_sample == 4) {
                const float* fData = (const float*)pData;
                for (UINT32 i = 0; i < numFrames; ++i) {
                    float sum = 0.0f;
                    for (int c = 0; c < channels; ++c) {
                        sum += fData[i * channels + c];
                    }
                    mono_samples[i] = sum / (float)channels;
                }
            } else if (bytes_per_sample == 2) { // 16-bit PCM
                const int16_t* sData = (const int16_t*)pData;
                for (UINT32 i = 0; i < numFrames; ++i) {
                    float sum = 0.0f;
                    for (int c = 0; c < channels; ++c) {
                        sum += (float)sData[i * channels + c] / 32768.0f;
                    }
                    mono_samples[i] = sum / (float)channels;
                }
            } else if (bytes_per_sample == 4) { // 32-bit int PCM
                const int32_t* iData = (const int32_t*)pData;
                for (UINT32 i = 0; i < numFrames; ++i) {
                    float sum = 0.0f;
                    for (int c = 0; c < channels; ++c) {
                        sum += (float)iData[i * channels + c] / 2147483648.0f;
                    }
                    mono_samples[i] = sum / (float)channels;
                }
            }
        }

        // 计算当前帧的 RMS 电平
        double sum_sq = 0.0;
        for (float s : mono_samples) {
            sum_sq += s * s;
        }
        float block_rms = (float)std::sqrt(sum_sq / (double)numFrames);
        float prev_lvl = current_level.load();
        current_level.store(prev_lvl * 0.7f + block_rms * 0.3f);

        // 2. 高质量线性插值重采样至 target_sample_rate
        std::vector<float> resampled;
        if (src_sample_rate == target_sample_rate) {
            resampled = std::move(mono_samples);
        } else {
            double step = (double)src_sample_rate / (double)target_sample_rate;
            double pos = resample_phase;
            size_t n = mono_samples.size();

            while (pos < (double)n) {
                int idx0 = (int)std::floor(pos);
                double frac = pos - idx0;
                float y0 = (idx0 >= 0) ? mono_samples[idx0] : last_input_sample;
                float y1 = (idx0 + 1 < (int)n) ? mono_samples[idx0 + 1] : y0;

                float interp = (float)(y0 + frac * (y1 - y0));
                resampled.push_back(interp);
                pos += step;
            }
            resample_phase = pos - (double)n;
            last_input_sample = mono_samples.empty() ? 0.0f : mono_samples.back();
        }

        if (resampled.empty()) return;

        // 3. 写入线程安全的环形缓冲区
        std::lock_guard<std::mutex> lock(buf_mutex);
        for (float val : resampled) {
            ring_buffer[ring_write_pos] = val;
            ring_write_pos = (ring_write_pos + 1) % ring_capacity;
            if (ring_count < ring_capacity) ring_count++;
            if (unread_count < ring_capacity) unread_count++;
            total_samples++;
        }
    }

private:
    std::wstring device_id;
    bool is_loopback;
    int target_sample_rate;
    float window_seconds;

    std::atomic<bool> running;
    std::atomic<float> current_level;
    std::thread capture_thread;

    mutable std::mutex buf_mutex;
    std::vector<float> ring_buffer;
    size_t ring_capacity;
    size_t ring_write_pos;
    size_t ring_count;
    size_t unread_count = 0;
    long long total_samples;

    double resample_phase;
    float last_input_sample;

    std::mutex err_mutex;
    std::string last_error;
};

// ==========================================
// C 语言导出的标准动态库接口
// ==========================================

WASAPI_API int wasapi_get_devices(WasapiDeviceInfo* devices, int max_devices) {
    HRESULT hr = CoInitializeEx(NULL, COINIT_MULTITHREADED);
    bool co_inited = SUCCEEDED(hr);

    IMMDeviceEnumerator* pEnumerator = NULL;
    hr = CoCreateInstance(__uuidof(MMDeviceEnumerator), NULL, CLSCTX_ALL,
                          __uuidof(IMMDeviceEnumerator), (void**)&pEnumerator);
    if (FAILED(hr) || !pEnumerator) {
        if (co_inited) CoUninitialize();
        return -1;
    }

    int device_index = 0;

    // 获取系统默认设备用于标记 is_default
    std::wstring def_render_id;
    std::wstring def_capture_id;

    IMMDevice* pDefRender = NULL;
    if (SUCCEEDED(pEnumerator->GetDefaultAudioEndpoint(eRender, eConsole, &pDefRender)) && pDefRender) {
        LPWSTR pStr = NULL;
        if (SUCCEEDED(pDefRender->GetId(&pStr)) && pStr) {
            def_render_id = pStr;
            CoTaskMemFree(pStr);
        }
        pDefRender->Release();
    }

    IMMDevice* pDefCapture = NULL;
    if (SUCCEEDED(pEnumerator->GetDefaultAudioEndpoint(eCapture, eConsole, &pDefCapture)) && pDefCapture) {
        LPWSTR pStr = NULL;
        if (SUCCEEDED(pDefCapture->GetId(&pStr)) && pStr) {
            def_capture_id = pStr;
            CoTaskMemFree(pStr);
        }
        pDefCapture->Release();
    }

    // 枚举辅助 Lambda
    auto enumerate_endpoints = [&](EDataFlow flow, int is_loopback) {
        IMMDeviceCollection* pCollection = NULL;
        if (FAILED(pEnumerator->EnumAudioEndpoints(flow, DEVICE_STATE_ACTIVE, &pCollection)) || !pCollection) {
            return;
        }

        UINT count = 0;
        pCollection->GetCount(&count);

        for (UINT i = 0; i < count; ++i) {
            IMMDevice* pDevice = NULL;
            if (FAILED(pCollection->Item(i, &pDevice)) || !pDevice) continue;

            LPWSTR pstrId = NULL;
            pDevice->GetId(&pstrId);

            IPropertyStore* pProps = NULL;
            PROPVARIANT varName;
            PropVariantInit(&varName);
            std::wstring friendly_name = L"Audio Device";

            if (SUCCEEDED(pDevice->OpenPropertyStore(STGM_READ, &pProps)) && pProps) {
                if (SUCCEEDED(pProps->GetValue(PKEY_Device_FriendlyName, &varName))) {
                    if (varName.pwszVal) {
                        friendly_name = varName.pwszVal;
                    }
                    PropVariantClear(&varName);
                }
                pProps->Release();
            }

            if (devices && device_index < max_devices) {
                WasapiDeviceInfo& info = devices[device_index];
                wcsncpy_s(info.id, WASAPI_DEVICE_ID_MAX, pstrId ? pstrId : L"", _TRUNCATE);
                wcsncpy_s(info.name, WASAPI_DEVICE_NAME_MAX, friendly_name.c_str(), _TRUNCATE);
                info.is_loopback = is_loopback;
                if (is_loopback) {
                    info.is_default = (pstrId && def_render_id == pstrId) ? 1 : 0;
                } else {
                    info.is_default = (pstrId && def_capture_id == pstrId) ? 1 : 0;
                }
            }

            if (pstrId) CoTaskMemFree(pstrId);
            pDevice->Release();
            device_index++;
        }
        pCollection->Release();
    };

    // 1. 枚举渲染设备（扬声器 Loopback）
    enumerate_endpoints(eRender, 1);
    // 2. 枚举输入设备（麦克风 Capture）
    enumerate_endpoints(eCapture, 0);

    pEnumerator->Release();
    if (co_inited) CoUninitialize();
    return device_index;
}

WASAPI_API WasapiCaptureHandle wasapi_create(const wchar_t* device_id, int is_loopback, int target_sample_rate, float window_sec) {
    std::wstring dev_id = device_id ? device_id : L"";
    if (target_sample_rate <= 0) target_sample_rate = 16000;
    if (window_sec <= 0.0f) window_sec = 30.0f;

    WasapiSession* session = new WasapiSession(dev_id, is_loopback != 0, target_sample_rate, window_sec);
    return (WasapiCaptureHandle)session;
}

WASAPI_API int wasapi_start(WasapiCaptureHandle handle) {
    if (!handle) return -1;
    WasapiSession* session = (WasapiSession*)handle;
    return session->start() ? 0 : -1;
}

WASAPI_API int wasapi_stop(WasapiCaptureHandle handle) {
    if (!handle) return -1;
    WasapiSession* session = (WasapiSession*)handle;
    session->stop();
    return 0;
}

WASAPI_API int wasapi_is_running(WasapiCaptureHandle handle) {
    if (!handle) return 0;
    WasapiSession* session = (WasapiSession*)handle;
    return session->is_active() ? 1 : 0;
}

WASAPI_API void wasapi_destroy(WasapiCaptureHandle handle) {
    if (!handle) return;
    WasapiSession* session = (WasapiSession*)handle;
    delete session;
}

WASAPI_API float wasapi_get_level(WasapiCaptureHandle handle) {
    if (!handle) return 0.0f;
    WasapiSession* session = (WasapiSession*)handle;
    return session->get_level();
}

WASAPI_API long long wasapi_get_total_samples(WasapiCaptureHandle handle) {
    if (!handle) return 0;
    WasapiSession* session = (WasapiSession*)handle;
    return session->get_total();
}

WASAPI_API int wasapi_snapshot(WasapiCaptureHandle handle, float seconds, float* out_buffer, int max_samples, double* out_start_sec) {
    if (!handle) return 0;
    WasapiSession* session = (WasapiSession*)handle;
    return session->snapshot(seconds, out_buffer, max_samples, out_start_sec);
}

WASAPI_API int wasapi_read_samples(WasapiCaptureHandle handle, float* out_buffer, int max_samples) {
    if (!handle) return 0;
    WasapiSession* session = (WasapiSession*)handle;
    return session->read_samples(out_buffer, max_samples);
}

WASAPI_API const char* wasapi_get_last_error(WasapiCaptureHandle handle) {
    static std::string g_err;
    if (!handle) return "Invalid handle";
    WasapiSession* session = (WasapiSession*)handle;
    g_err = session->get_last_error();
    return g_err.c_str();
}
