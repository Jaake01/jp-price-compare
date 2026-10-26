// 掃描條碼：只用瀏覽器內建的 BarcodeDetector（Android Chrome 支援；iPhone Safari 不支援，按鈕不顯示）。
const WANTED = ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128', 'code_39', 'itf'];
const INTERVAL_MS = 150;

export function scanSupported() {
  return 'BarcodeDetector' in window && !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
}

/**
 * 開相機掃描，連續兩次讀到同一個號碼才算數（避免誤讀）。
 * 回傳 { promise, stop }；promise 解析為條碼字串，取消時為 null。
 */
export function startScan(video) {
  let stopped = false;
  let stream = null;
  let timer = null;
  let finish;
  const promise = new Promise((resolve, reject) => {
    finish = (val, err) => {
      if (stopped) return;
      stopped = true;
      clearTimeout(timer);
      if (stream) stream.getTracks().forEach((t) => t.stop());
      video.srcObject = null;
      err ? reject(err) : resolve(val);
    };
  });
  (async () => {
    try {
      const supported = await window.BarcodeDetector.getSupportedFormats();
      const formats = WANTED.filter((f) => supported.includes(f));
      const detector = new window.BarcodeDetector(formats.length ? { formats } : undefined);
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
      if (stopped) { stream.getTracks().forEach((t) => t.stop()); return; }
      video.srcObject = stream;
      await video.play();
      let last = null;
      const tick = async () => {
        if (stopped) return;
        try {
          const codes = await detector.detect(video);
          const val = codes.length ? String(codes[0].rawValue || '').trim() : null;
          if (val && val === last) return finish(val);
          last = val;
        } catch (e) { /* 這一格辨識失敗就換下一格 */ }
        timer = setTimeout(tick, INTERVAL_MS);
      };
      tick();
    } catch (e) {
      finish(null, e);
    }
  })();
  return { promise, stop: () => finish(null) };
}
