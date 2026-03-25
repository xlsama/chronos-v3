import { useEffect, useState } from "react";
import { motion } from "motion/react";

interface AudioVisualizerProps {
  analyserNode: AnalyserNode | null;
  className?: string;
}

const BAR_COUNT = 5;

export function AudioVisualizer({ analyserNode, className }: AudioVisualizerProps) {
  const [levels, setLevels] = useState<number[]>(new Array(BAR_COUNT).fill(0));

  useEffect(() => {
    if (!analyserNode) return;

    const dataArray = new Uint8Array(analyserNode.frequencyBinCount);
    let raf: number;

    function update() {
      analyserNode!.getByteFrequencyData(dataArray);
      const step = Math.floor(dataArray.length / BAR_COUNT);
      const newLevels = Array.from({ length: BAR_COUNT }, (_, i) => dataArray[i * step] / 255);
      setLevels(newLevels);
      raf = requestAnimationFrame(update);
    }
    update();

    return () => cancelAnimationFrame(raf);
  }, [analyserNode]);

  return (
    <div className={`flex items-center gap-1 ${className ?? ""}`} style={{ height: 32 }}>
      {levels.map((level, i) => (
        <motion.div
          key={i}
          className="bg-primary w-1 rounded-full"
          animate={{ height: Math.max(4, level * 28) }}
          transition={{ type: "spring", stiffness: 300, damping: 20 }}
        />
      ))}
    </div>
  );
}
