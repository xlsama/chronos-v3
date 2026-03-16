import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";

type VoiceState = "idle" | "connecting" | "recording" | "error";

interface UseVoiceInputOptions {
  onTranscript: (text: string) => void;
}

interface UseVoiceInputReturn {
  state: VoiceState;
  interimText: string;
  analyserNode: AnalyserNode | null;
  startRecording: () => Promise<void>;
  stopRecording: () => void;
  cancelRecording: () => void;
}

export function useVoiceInput({
  onTranscript,
}: UseVoiceInputOptions): UseVoiceInputReturn {
  const [state, setState] = useState<VoiceState>("idle");
  const [interimText, setInterimText] = useState("");
  const [analyserNode, setAnalyserNode] = useState<AnalyserNode | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const finalTextRef = useRef("");
  const cancelledRef = useRef(false);
  const onTranscriptRef = useRef(onTranscript);
  onTranscriptRef.current = onTranscript;

  const cleanup = useCallback(() => {
    workletNodeRef.current?.disconnect();
    workletNodeRef.current = null;

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

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setAnalyserNode(null);
    setInterimText("");
    finalTextRef.current = "";
  }, []);

  const startRecording = useCallback(async () => {
    if (state !== "idle") return;

    cancelledRef.current = false;
    finalTextRef.current = "";
    setInterimText("");
    setState("connecting");

    // Check AudioWorklet support
    if (typeof AudioWorkletNode === "undefined") {
      toast.error("当前浏览器不支持语音输入");
      setState("idle");
      return;
    }

    // Get microphone
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
        },
      });
    } catch (err) {
      const name = (err as DOMException).name;
      if (name === "NotAllowedError") {
        toast.error("麦克风权限被拒绝");
      } else if (name === "NotFoundError") {
        toast.error("未检测到麦克风设备");
      } else {
        toast.error("无法访问麦克风");
      }
      setState("idle");
      return;
    }
    streamRef.current = stream;

    // Setup AudioContext + Worklet
    let audioContext: AudioContext;
    try {
      audioContext = new AudioContext({ sampleRate: 16000 });
      await audioContext.audioWorklet.addModule("/pcm-processor.js");
    } catch {
      toast.error("音频初始化失败");
      cleanup();
      setState("idle");
      return;
    }
    audioContextRef.current = audioContext;

    const source = audioContext.createMediaStreamSource(stream);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    setAnalyserNode(analyser);

    const workletNode = new AudioWorkletNode(audioContext, "pcm-processor");
    analyser.connect(workletNode);
    workletNode.connect(audioContext.destination);
    workletNodeRef.current = workletNode;

    // Setup WebSocket
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${location.host}/api/asr/stream`);
    wsRef.current = ws;

    ws.onopen = () => {
      if (cancelledRef.current) {
        ws.close();
        return;
      }
      setState("recording");
    };

    ws.onerror = () => {
      if (!cancelledRef.current) {
        toast.error("语音识别连接失败");
      }
      cleanup();
      setState("idle");
    };

    ws.onclose = () => {
      if (state === "recording" && !cancelledRef.current) {
        // Unexpected close
      }
    };

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === "result") {
          if (msg.is_end) {
            if (msg.text) {
              finalTextRef.current += msg.text;
            }
            setInterimText("");
          } else {
            setInterimText(msg.text || "");
          }
        } else if (msg.type === "finished") {
          if (!cancelledRef.current && finalTextRef.current) {
            onTranscriptRef.current(finalTextRef.current);
          }
          cleanup();
          setState("idle");
        } else if (msg.type === "error") {
          if (!cancelledRef.current) {
            toast.error(msg.message || "语音识别失败");
          }
          cleanup();
          setState("idle");
        }
      } catch {
        // ignore parse errors
      }
    };

    // Forward PCM from worklet to WS
    workletNode.port.onmessage = (e) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(e.data as ArrayBuffer);
      }
    };
  }, [state, cleanup]);

  const stopRecording = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: "stop" }));
    }
    if (!cancelledRef.current && finalTextRef.current) {
      onTranscriptRef.current(finalTextRef.current);
    }
    cleanup();
    setState("idle");
  }, [cleanup]);

  const cancelRecording = useCallback(() => {
    cancelledRef.current = true;
    cleanup();
    setState("idle");
  }, [cleanup]);

  return {
    state,
    interimText,
    analyserNode,
    startRecording,
    stopRecording,
    cancelRecording,
  };
}
