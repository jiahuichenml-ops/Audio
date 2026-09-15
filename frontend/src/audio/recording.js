export const MIN_DURATION_MS = 1000;
export const MAX_DURATION_MS = 60_000;
export const MAX_AUDIO_BYTES = 5 * 1024 * 1024;

const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
];

export function detectRecordingMimeType() {
  if (
    typeof MediaRecorder === "undefined" ||
    typeof MediaRecorder.isTypeSupported !== "function"
  ) {
    return null;
  }
  return MIME_CANDIDATES.find((type) => MediaRecorder.isTypeSupported(type)) ?? null;
}

export function extensionForMimeType(mimeType) {
  if (mimeType?.includes("ogg")) {
    return "ogg";
  }
  return "webm";
}

export function stopMediaStream(stream) {
  if (!stream) {
    return;
  }
  for (const track of stream.getTracks()) {
    track.stop();
  }
}

export function formatDuration(ms) {
  const totalSeconds = Math.max(0, ms / 1000);
  return `${totalSeconds.toFixed(1)} 秒`;
}

export function formatBytes(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function permissionErrorMessage(error) {
  const name = error?.name ?? "";
  if (name === "NotAllowedError" || name === "PermissionDeniedError") {
    return "麦克风权限被拒绝，请在浏览器中允许使用麦克风后再试。";
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return "未找到可用的麦克风，请检查设备后重试。";
  }
  if (name === "NotReadableError" || name === "TrackStartError") {
    return "麦克风被占用，请关闭其他正在使用麦克风的应用后重试。";
  }
  if (name === "SecurityError") {
    return "当前页面无法访问麦克风，请使用本地 http://127.0.0.1:5175 打开。";
  }
  return "录音失败，请检查麦克风后重试。";
}
