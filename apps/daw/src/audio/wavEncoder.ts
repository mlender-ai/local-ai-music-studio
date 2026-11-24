/**
 * Encode an AudioBuffer (or raw Float32 stereo channels) into a standards-compliant
 * 24-bit PCM Stereo RIFF/WAV ArrayBuffer.
 */
export function encodeStereoWav24(
  left: Float32Array,
  right: Float32Array,
  sampleRate: number
): ArrayBuffer {
  const numChannels = 2;
  const bytesPerSample = 3; // 24-bit PCM
  const frameCount = Math.min(left.length, right.length);
  const dataSize = frameCount * numChannels * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  const writeStr = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  };

  writeStr(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true); // PCM chunk size
  view.setUint16(20, 1, true); // AudioFormat = PCM
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * numChannels * bytesPerSample, true);
  view.setUint16(32, numChannels * bytesPerSample, true);
  view.setUint16(34, 24, true); // BitsPerSample
  writeStr(36, "data");
  view.setUint32(40, dataSize, true);

  const bytes = new Uint8Array(buffer, 44);
  let ptr = 0;
  const scale = 8388607; // 2^23 - 1
  for (let i = 0; i < frameCount; i++) {
    for (let ch = 0; ch < 2; ch++) {
      const sample = Math.max(-1, Math.min(1, ch === 0 ? left[i] : right[i]));
      const intVal = Math.round(sample * scale);
      bytes[ptr++] = intVal & 0xff;
      bytes[ptr++] = (intVal >> 8) & 0xff;
      bytes[ptr++] = (intVal >> 16) & 0xff;
    }
  }

  return buffer;
}

export function audioBufferToWavBlob(audioBuffer: AudioBuffer): Blob {
  const left = audioBuffer.getChannelData(0);
  const right = audioBuffer.numberOfChannels > 1 ? audioBuffer.getChannelData(1) : left;
  const wav = encodeStereoWav24(left, right, audioBuffer.sampleRate);
  return new Blob([wav], { type: "audio/wav" });
}
