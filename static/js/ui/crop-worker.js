self.onmessage = async (event) => {
  const { file, sx, sy, sw, sh, width, height, type, quality } = event.data;
  try {
    const bitmap = await createImageBitmap(file);
    const canvas = new OffscreenCanvas(width, height);
    canvas.getContext('2d').drawImage(bitmap, sx, sy, sw, sh, 0, 0, width, height);
    self.postMessage({ blob: await canvas.convertToBlob({ type, quality }) });
  } catch (error) {
    self.postMessage({ error: error && error.message ? error.message : String(error) });
  }
};
