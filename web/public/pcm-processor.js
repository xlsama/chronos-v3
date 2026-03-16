class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Float32Array(0);
    this._chunkSize = 3200; // 200ms @ 16kHz
  }

  process(inputs) {
    const input = inputs[0]?.[0];
    if (!input) return true;

    // Append new samples to buffer
    const newBuffer = new Float32Array(this._buffer.length + input.length);
    newBuffer.set(this._buffer);
    newBuffer.set(input, this._buffer.length);
    this._buffer = newBuffer;

    // Send complete chunks
    while (this._buffer.length >= this._chunkSize) {
      const chunk = this._buffer.slice(0, this._chunkSize);
      this._buffer = this._buffer.slice(this._chunkSize);

      // Float32 → Int16 PCM
      const pcm = new Int16Array(chunk.length);
      for (let i = 0; i < chunk.length; i++) {
        const s = Math.max(-1, Math.min(1, chunk[i]));
        pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
    }

    return true;
  }
}

registerProcessor("pcm-processor", PCMProcessor);
