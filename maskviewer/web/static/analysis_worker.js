// Web Worker: runs the per-recording analysis (tables_engine.analyseStack + ensemble curves) off the page's main
// thread and posts progress. Message in: {id, labels (Int32Array), T, H, W, umPerPx, dtMin}.
import { analyseStack, recordingCurves } from './tables_engine.js';

self.onmessage = e => {
  const { id, labels, T, H, W, umPerPx, dtMin } = e.data;
  try {
    const m = { labels, T, H, W };
    const res = analyseStack(m, { umPerPx, dtMin, onFrame: (d, n) => self.postMessage({ id, progress: d / n }) });
    res.curves = recordingCurves(res.cents, { umPerPx, dtMin });
    self.postMessage({ id, result: res });
  } catch (err) {
    self.postMessage({ id, error: err.message });
  }
};
