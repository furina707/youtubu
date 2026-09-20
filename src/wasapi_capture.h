#ifndef WASAPI_CAPTURE_H
#define WASAPI_CAPTURE_H

#ifdef __cplusplus
extern "C" {
#endif

#if defined(_WIN32) || defined(__CYGWIN__)
  #ifdef WASAPI_CAPTURE_EXPORTS
    #define WASAPI_API __declspec(dllexport)
  #else
    #define WASAPI_API __declspec(dllimport)
  #endif
#else
  #define WASAPI_API
#endif

typedef void* WasapiCaptureHandle;

#define WASAPI_DEVICE_NAME_MAX 256
#define WASAPI_DEVICE_ID_MAX 256

typedef struct {
    wchar_t id[WASAPI_DEVICE_ID_MAX];
    wchar_t name[WASAPI_DEVICE_NAME_MAX];
    int is_loopback;   /* 1: 扬声器回环录制(系统正在播放的声音); 0: 麦克风录制 */
    int is_default;    /* 1: 系统默认设备; 0: 非默认 */
} WasapiDeviceInfo;

/*
 * 枚举所有可用的音频输入设备（包含扬声器 Loopback 与麦克风）
 * - devices: 用于接收设备信息的数组指针，传 NULL 时仅返回总设备数
 * - max_devices: devices 数组容量
 * 返回值：实际找到的设备总数，失败返回 -1
 */
WASAPI_API int wasapi_get_devices(WasapiDeviceInfo* devices, int max_devices);

/*
 * 创建音频捕获会话
 * - device_id: 设备 ID（宽字符字符串），传 NULL 或空字符串则自动选默认设备
 * - is_loopback: 1 为系统扬声器输出 (Loopback)，0 为麦克风
 * - target_sample_rate: 目标采样率（如 16000），内部自适应高质量线性重采样
 * - window_sec: 环形缓冲保留的最大时长（秒），例如 30.0
 * 返回值：实例句柄，失败返回 NULL
 */
WASAPI_API WasapiCaptureHandle wasapi_create(const wchar_t* device_id, int is_loopback, int target_sample_rate, float window_sec);

/*
 * 启动音频捕获线程
 * 返回值：0 成功，非 0 失败
 */
WASAPI_API int wasapi_start(WasapiCaptureHandle handle);

/*
 * 停止音频捕获线程
 * 返回值：0 成功，非 0 失败
 */
WASAPI_API int wasapi_stop(WasapiCaptureHandle handle);

/*
 * 查询是否正在运行
 */
WASAPI_API int wasapi_is_running(WasapiCaptureHandle handle);

/*
 * 销毁会话并释放所有 COM 与内存资源
 */
WASAPI_API void wasapi_destroy(WasapiCaptureHandle handle);

/*
 * 获取当前瞬时音频电平 RMS (0.0 ~ 1.0)
 */
WASAPI_API float wasapi_get_level(WasapiCaptureHandle handle);

/*
 * 获取自启动以来累计录制的样本数 (以 target_sample_rate 为基准)
 */
WASAPI_API long long wasapi_get_total_samples(WasapiCaptureHandle handle);

/*
 * 截取最近 seconds 秒的音频样本（16k float32 mono），供语音识别模型推断
 * - seconds: 截取最近多少秒
 * - out_buffer: 存放输出样本的 float 数组
 * - max_samples: out_buffer 容量
 * - out_start_sec: 输出该段音频在整条时间线上的起始绝对秒数
 * 返回值：实际输出的样本数
 */
WASAPI_API int wasapi_snapshot(WasapiCaptureHandle handle, float seconds, float* out_buffer, int max_samples, double* out_start_sec);

/*
 * 轮询读取新到达的音频样本（从上次读取位置起）
 * 返回值：实际读取的样本数
 */
WASAPI_API int wasapi_read_samples(WasapiCaptureHandle handle, float* out_buffer, int max_samples);

/*
 * 获取最后一次错误信息字符串 (UTF-8 编码)
 */
WASAPI_API const char* wasapi_get_last_error(WasapiCaptureHandle handle);

#ifdef __cplusplus
}
#endif

#endif /* WASAPI_CAPTURE_H */
