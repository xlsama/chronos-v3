import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { transcribeAudio } from "@/api/asr";

type VoiceState = "idle" | "recording" | "transcribing";

interface UseVoiceInputOptions {
  onTranscript: (text: string) => void;
  onCancel?: () => void;
}

interface UseVoiceInputReturn {
  state: VoiceState;
  analyserNode: AnalyserNode | null;
  startRecording: () => Promise<void>;
  stopRecording: () => void;
  cancelRecording: () => void;
}

export function useVoiceInput({
  onTranscript,
  onCancel,
}: UseVoiceInputOptions): UseVoiceInputReturn {
  const [state, setState] = useState<VoiceState>("idle");
  const [analyserNode, setAnalyserNode] = useState<AnalyserNode | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const cancelledRef = useRef(false);
  const onTranscriptRef = useRef(onTranscript);
  const onCancelRef = useRef(onCancel);
  useEffect(() => {
    onTranscriptRef.current = onTranscript;
    onCancelRef.current = onCancel;
  });

  const cleanup = useCallback(() => {
    if (streamRef.current) {
      for (const track of streamRef.current.getTracks()) {
        track.stop();
      }
      streamRef.current = null;
    }

    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }

    mediaRecorderRef.current = null;
    chunksRef.current = [];
    setAnalyserNode(null);
  }, []);

  const startRecording = useCallback(async () => {
    if (state !== "idle") return;

    cancelledRef.current = false;
    chunksRef.current = [];

    // Get microphone
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      const name = (err as DOMException).name;
      if (name === "NotAllowedError") {
        toast.error("麦克风权限被拒绝");
      } else if (name === "NotFoundError") {
        toast.error("未检测到麦克风设备");
      } else {
        toast.error("无法访问麦克风");
      }
      return;
    }
    streamRef.current = stream;

    // Setup AudioContext + AnalyserNode for visualization
    const audioContext = new AudioContext();
    audioContextRef.current = audioContext;
    const source = audioContext.createMediaStreamSource(stream);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    setAnalyserNode(analyser);

    // Setup MediaRecorder
    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : undefined;

    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    mediaRecorderRef.current = recorder;

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) {
        chunksRef.current.push(e.data);
      }
    };

    recorder.onstop = async () => {
      if (cancelledRef.current) {
        cleanup();
        return;
      }

      const chunks = chunksRef.current;
      if (chunks.length === 0) {
        cleanup();
        setState("idle");
        return;
      }

      const blob = new Blob(chunks, { type: recorder.mimeType });
      cleanup();
      setState("transcribing");

      try {
        const { text } = await transcribeAudio(blob);
        if (text && !cancelledRef.current) {
          onTranscriptRef.current(text);
        } else if (!cancelledRef.current) {
          toast.info("未识别到语音内容");
        }
      } catch {
        if (!cancelledRef.current) {
          toast.error("语音识别失败");
        }
      }
      setState("idle");
    };

    recorder.start();
    setState("recording");
  }, [state, cleanup]);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }
  }, []);

  const cancelRecording = useCallback(() => {
    cancelledRef.current = true;
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }
    cleanup();
    onCancelRef.current?.();
    setState("idle");
  }, [cleanup]);

  return {
    state,
    analyserNode,
    startRecording,
    stopRecording,
    cancelRecording,
  };
}
