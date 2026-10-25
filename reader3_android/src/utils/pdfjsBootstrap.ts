// Both WebViews load the same bundled module and worker without a network fallback.
export const PDFJS_BOOTSTRAP = `<script src="file:///android_asset/pdfjs/polyfills.js"></script>
<script>
window.pdfjsReady = import('file:///android_asset/pdfjs/pdf.min.mjs').then(function(lib) {
    window.pdfjsLib = lib;
    lib.GlobalWorkerOptions.workerSrc = 'file:///android_asset/pdfjs/pdf.worker.bootstrap.mjs';
    return lib;
});
// The load operation reports failures through the existing WebView message handler.
window.pdfjsReady.catch(function() {});
</script>`;

export const PDFJS_DOCUMENT_OPTIONS = `
    isEvalSupported: false,
    cMapUrl: 'file:///android_asset/pdfjs/cmaps/',
    cMapPacked: true,
    standardFontDataUrl: 'file:///android_asset/pdfjs/standard_fonts/',
    wasmUrl: 'file:///android_asset/pdfjs/wasm/',
`;
