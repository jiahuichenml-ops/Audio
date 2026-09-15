import { useEffect, useRef, useState } from "react";
import {
  MAX_AUDIO_BYTES,
  MAX_DURATION_MS,
  MIN_DURATION_MS,
  detectRecordingMimeType,
  extensionForMimeType,
  formatBytes,
  formatDuration,
  permissionErrorMessage,
  stopMediaStream,
} from "../audio/recording.js";

export default function RecordPanel() {
  const mimeType = detectRecordingMimeType();
  const [error, setError] = useState(
    mimeType
      ? ""
      : "当前浏览器不支持 WebM/Opus 录音，请更换 Chrome 或 Edge 后再试。",
  );
  const [phase, setPhase] = useState("idle");
  const [elapsedMs, setElapsedMs] = useState(0);
  const [clip, setClip] = useState(null);

  const sessionRef = useRef(0);
  const pendingStopRef = useRef(false);
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const startedAtRef = useRef(0);
  const maxTimerRef = useRef(0);
  const tickTimerRef = useRef(0);
  const clipUrlRef = useRef("");
  const phaseRef = useRef("idle");

  function setPhaseSafe(next) {
    phaseRef.current = next;
    setPhase(next);
  }

  function clearTimers() {
    window.clearTimeout(maxTimerRef.current);
    window.clearInterval(tickTimerRef.current);
    maxTimerRef.current = 0;
    tickTimerRef.current = 0;
  }

  function releaseMicrophone() {
    stopMediaStream(streamRef.current);
    streamRef.current = null;
  }

  function revokeClipUrl() {
    if (clipUrlRef.current) {
      URL.revokeObjectURL(clipUrlRef.current);
      clipUrlRef.current = "";
    }
  }

  function resetRecorder() {
    clearTimers();
    const recorder = recorderRef.current;
    recorderRef.current = null;
    if (recorder && recorder.state === "recording") {
      try {
        recorder.stop();
      } catch {
        // Already stopping or inactive.
      }
    }
    releaseMicrophone();
    chunksRef.current = [];
    startedAtRef.current = 0;
  }

  useEffect(() => {
    return () => {
      sessionRef.current += 1;
      pendingStopRef.current = true;
      resetRecorder();
      revokeClipUrl();
    };
  }, []);

  useEffect(() => {
    if (phase !== "recording" && phase !== "starting") {
      return undefined;
    }
    function onKeyDown(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        cancelRecording();
      }
    }
    function onWindowPointerUp() {
      if (phaseRef.current === "recording") {
        finishRecording();
      }
    }
    function onVisibilityChange() {
      if (document.hidden) {
        cancelRecording();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("pointerup", onWindowPointerUp);
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("pointerup", onWindowPointerUp);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [phase]);

  function beginTimers() {
    startedAtRef.current = Date.now();
    setElapsedMs(0);
    tickTimerRef.current = window.setInterval(() => {
      setElapsedMs(Date.now() - startedAtRef.current);
    }, 200);
    maxTimerRef.current = window.setTimeout(() => {
      finishRecording();
    }, MAX_DURATION_MS);
  }

  function finishRecording() {
    pendingStopRef.current = true;
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") {
      if (phaseRef.current === "starting") {
        resetRecorder();
        setPhaseSafe("idle");
      }
      return;
    }
    try {
      recorder.stop();
    } catch (error) {
      resetRecorder();
      setPhaseSafe("idle");
      setError(permissionErrorMessage(error));
    }
  }

  function cancelRecording() {
    sessionRef.current += 1;
    pendingStopRef.current = true;
    resetRecorder();
    setElapsedMs(0);
    setPhaseSafe("idle");
    setError("已取消录音。");
  }

  async function startRecording() {
    if (
      !mimeType ||
      phaseRef.current === "recording" ||
      phaseRef.current === "starting"
    ) {
      return;
    }

    pendingStopRef.current = false;
    const session = sessionRef.current + 1;
    sessionRef.current = session;
    setError("");
    setPhaseSafe("starting");

    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (error) {
      if (sessionRef.current !== session) {
        return;
      }
      setPhaseSafe("idle");
      setError(permissionErrorMessage(error));
      return;
    }

    if (sessionRef.current !== session || pendingStopRef.current) {
      stopMediaStream(stream);
      setPhaseSafe("idle");
      return;
    }

    streamRef.current = stream;
    chunksRef.current = [];

    let recorder;
    try {
      recorder = new MediaRecorder(stream, { mimeType });
    } catch (error) {
      stopMediaStream(stream);
      streamRef.current = null;
      setPhaseSafe("idle");
      setError(permissionErrorMessage(error));
      return;
    }

    recorderRef.current = recorder;
    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        chunksRef.current.push(event.data);
      }
    };
    recorder.onerror = () => {
      if (sessionRef.current !== session) {
        return;
      }
      resetRecorder();
      setPhaseSafe("idle");
      setError("录制失败，请检查麦克风后重试。");
    };
    recorder.onstop = () => {
      if (sessionRef.current !== session) {
        releaseMicrophone();
        return;
      }
      const durationMs = Date.now() - startedAtRef.current;
      const blob = new Blob(chunksRef.current, { type: mimeType });
      resetRecorder();
      setElapsedMs(durationMs);

      if (durationMs < MIN_DURATION_MS) {
        setPhaseSafe("idle");
        setError("录音时间太短，请按住至少 1 秒。");
        return;
      }
      if (blob.size > MAX_AUDIO_BYTES) {
        setPhaseSafe("idle");
        setError("录音文件过大（超过 5MB），请缩短录音时间。");
        return;
      }
      if (blob.size === 0) {
        setPhaseSafe("idle");
        setError("没有录到有效音频，请重试。");
        return;
      }

      revokeClipUrl();
      const url = URL.createObjectURL(blob);
      clipUrlRef.current = url;
      const filename = `meetup-recording.${extensionForMimeType(mimeType)}`;
      setClip({ blob, url, filename, durationMs, mimeType });
      setPhaseSafe("idle");
    };

    try {
      recorder.start();
    } catch (error) {
      resetRecorder();
      setPhaseSafe("idle");
      setError(permissionErrorMessage(error));
      return;
    }

    setPhaseSafe("recording");
    beginTimers();

    if (pendingStopRef.current) {
      finishRecording();
    }
  }

  function onPointerDown(event) {
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    startRecording();
  }

  function onPointerUp() {
    finishRecording();
  }

  function onPointerCancel() {
    cancelRecording();
  }

  const unsupported = !mimeType;
  const holding = phase === "recording" || phase === "starting";

  return (
    <section className="panel">
      <p className="hint">按住按钮说话，松开结束。本轮只做本地录音，不会上传或识别。</p>
      <button
        type="button"
        className={holding ? "record-btn recording" : "record-btn"}
        disabled={unsupported}
        onPointerDown={onPointerDown}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerCancel}
        onContextMenu={(event) => event.preventDefault()}
      >
        {holding ? `录音中 ${formatDuration(elapsedMs)}` : "按住说话"}
      </button>
      <p className="meta">
        {mimeType
          ? `将使用浏览器实际支持的格式：${mimeType}。时长 1–60 秒，文件不超过 5MB。按 Esc 可取消。`
          : "未检测到可用的 WebM/Opus 录音能力。"}
      </p>
      {error ? <p className="error">{error}</p> : null}
      {clip ? (
        <div className="clip">
          <p>录音完成，可先本地试听，再下载文件供后续上传接口测试。</p>
          <p className="meta">
            格式 {clip.mimeType} · 大小 {formatBytes(clip.blob.size)} · 按时戳计算时长{" "}
            {formatDuration(clip.durationMs)}
          </p>
          <audio controls src={clip.url} />
          <p>
            <a href={clip.url} download={clip.filename}>
              下载录音文件
            </a>
          </p>
        </div>
      ) : null}
    </section>
  );
}
