class PCMProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const opts = options.processorOptions || {};
    this.targetRate = opts.targetSampleRate || 16000;
    this.frameSamples = opts.frameSamples || 320;
    this.sourceRate = sampleRate;
    this.ratio = this.sourceRate / this.targetRate;
    this.pending = [];
    this.port.onmessage = (event) => {
      if (event.data && event.data.type === "init") {
        this.port.postMessage({ status: "ready" });
      }
    };
  }

  process(inputs, outputs) {
    const input = inputs[0];
    if (!input || !input[0] || input[0].length === 0) {
      this._zeroOutput(outputs);
      return true;
    }

    const channel = input[0];
    const resampled = this._resample(channel);

    for (let i = 0; i < resampled.length; i += 1) {
      this.pending.push(resampled[i]);
    }

    while (this.pending.length >= this.frameSamples) {
      const frame = this.pending.slice(0, this.frameSamples);
      this.pending = this.pending.slice(this.frameSamples);

      let sumSquares = 0;
      const pcm = new Int16Array(this.frameSamples);
      for (let i = 0; i < frame.length; i += 1) {
        const sample = Math.max(-1, Math.min(1, frame[i]));
        sumSquares += sample * sample;
        pcm[i] = sample < 0 ? sample * 32768 : sample * 32767;
      }

      const rms = Math.sqrt(sumSquares / frame.length) * 32768;
      this.port.postMessage(
        { pcm: pcm.buffer, rms },
        [pcm.buffer]
      );
    }

    this._zeroOutput(outputs);
    return true;
  }

  _resample(input) {
    const outputLength = Math.floor(input.length / this.ratio);
    const output = new Float32Array(outputLength);
    for (let i = 0; i < outputLength; i += 1) {
      const index = i * this.ratio;
      const i0 = Math.floor(index);
      const i1 = Math.min(i0 + 1, input.length - 1);
      const frac = index - i0;
      output[i] = input[i0] + (input[i1] - input[i0]) * frac;
    }
    return output;
  }

  _zeroOutput(outputs) {
    if (!outputs || outputs.length === 0) return;
    const output = outputs[0];
    if (!output || output.length === 0) return;
    for (let channel = 0; channel < output.length; channel += 1) {
      output[channel].fill(0);
    }
  }
}

registerProcessor("pcm-processor", PCMProcessor);
