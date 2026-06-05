export const SAMPLE_RATE = 16_000;
export const CHUNK_DURATION_MS = 900;
export const CHUNK_SAMPLE_TARGET = Math.floor((SAMPLE_RATE * CHUNK_DURATION_MS) / 1000);

export function mergePcmChunks(chunks: Int16Array[]) {
  const totalLength = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const merged = new Int16Array(totalLength);
  let offset = 0;

  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }

  return merged;
}

export function encodeWav(pcmData: Int16Array, sampleRate: number) {
  const buffer = new ArrayBuffer(44 + pcmData.length * 2);
  const view = new DataView(buffer);

  const writeString = (offset: number, value: string) => {
    for (let index = 0; index < value.length; index += 1) {
      view.setUint8(offset + index, value.charCodeAt(index));
    }
  };

  writeString(0, "RIFF");
  view.setUint32(4, 36 + pcmData.length * 2, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(36, "data");
  view.setUint32(40, pcmData.length * 2, true);

  let offset = 44;
  for (let index = 0; index < pcmData.length; index += 1) {
    view.setInt16(offset, pcmData[index], true);
    offset += 2;
  }

  return new Blob([buffer], { type: "audio/wav" });
}

export function floatToPcmChunk(input: Float32Array) {
  const pcm = new Int16Array(input.length);
  for (let index = 0; index < input.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, input[index]));
    pcm[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return pcm;
}

export function analyzePcmChunk(input: Int16Array) {
  if (!input.length) {
    return {
      rms: 0,
      peak: 0,
      zeroCrossingRate: 0,
    };
  }

  let sumSquares = 0;
  let peak = 0;
  let zeroCrossings = 0;

  for (let index = 0; index < input.length; index += 1) {
    const normalized = input[index] / 32768;
    sumSquares += normalized * normalized;
    peak = Math.max(peak, Math.abs(normalized));

    if (index > 0) {
      const previous = input[index - 1];
      const current = input[index];
      if ((previous >= 0 && current < 0) || (previous < 0 && current >= 0)) {
        zeroCrossings += 1;
      }
    }
  }

  return {
    rms: Math.sqrt(sumSquares / input.length),
    peak,
    zeroCrossingRate: zeroCrossings / input.length,
  };
}
