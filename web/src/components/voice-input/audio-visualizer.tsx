import { useEffect, useRef } from "react";

interface AudioVisualizerProps {
  analyserNode: AnalyserNode | null;
  className?: string;
}

export function AudioVisualizer({
  analyserNode,
  className,
}: AudioVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !analyserNode) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dataArray = new Uint8Array(analyserNode.frequencyBinCount);
    const barCount = 24;
    const barGap = 3;

    function draw() {
      animationRef.current = requestAnimationFrame(draw);
      analyserNode!.getByteFrequencyData(dataArray);

      const { width, height } = canvas!;
      ctx!.clearRect(0, 0, width, height);

      const totalBarWidth = (width - barGap * (barCount - 1)) / barCount;
      const barWidth = Math.max(2, totalBarWidth);
      const centerY = height / 2;

      // Sample frequency bins evenly
      const step = Math.floor(dataArray.length / barCount);

      for (let i = 0; i < barCount; i++) {
        const value = dataArray[i * step] / 255;
        const barHeight = Math.max(4, value * height * 0.8);

        const x = i * (barWidth + barGap);

        ctx!.fillStyle = `oklch(0.55 0.15 260 / ${0.5 + value * 0.5})`;
        ctx!.beginPath();
        ctx!.roundRect(x, centerY - barHeight / 2, barWidth, barHeight, barWidth / 2);
        ctx!.fill();
      }
    }

    draw();

    return () => {
      cancelAnimationFrame(animationRef.current);
    };
  }, [analyserNode]);

  return (
    <canvas
      ref={canvasRef}
      width={200}
      height={48}
      className={className}
    />
  );
}
