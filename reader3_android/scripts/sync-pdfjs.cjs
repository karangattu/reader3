const { copyFileSync, cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } = require('node:fs');
const path = require('node:path');

// Copy the library and worker from the same locked package for offline WebViews.
function syncPdfjs(destination) {
    const source = path.dirname(require.resolve('pdfjs-dist/package.json'));
    rmSync(destination, { recursive: true, force: true });
    mkdirSync(destination, { recursive: true });
    for (const name of ['pdf.min.mjs', 'pdf.worker.min.mjs']) {
        copyFileSync(path.join(source, 'legacy', 'build', name), path.join(destination, name));
    }
    for (const directory of ['cmaps', 'standard_fonts', 'wasm']) {
        cpSync(path.join(source, directory), path.join(destination, directory), { recursive: true });
    }
    copyFileSync(path.join(source, 'LICENSE'), path.join(destination, 'LICENSE'));
    const polyfills = path.dirname(require.resolve('core-js-bundle/package.json'));
    const streams = require.resolve('web-streams-polyfill/polyfill');
    writeFileSync(path.join(destination, 'polyfills.js'),
        readFileSync(path.join(polyfills, 'minified.js'), 'utf8') +
        '\nif (typeof ReadableStream === "undefined" || !ReadableStream.prototype[Symbol.asyncIterator]) {\n' +
        readFileSync(streams, 'utf8') + '\n}\n');
    copyFileSync(path.join(polyfills, 'LICENSE'), path.join(destination, 'LICENSE.core-js'));
    copyFileSync(path.join(path.dirname(streams), '..', 'LICENSE'), path.join(destination, 'LICENSE.web-streams'));
    writeFileSync(path.join(destination, 'pdf.worker.bootstrap.mjs'),
        "import './polyfills.js';\nexport { WorkerMessageHandler } from './pdf.worker.min.mjs';\n");
}

module.exports = syncPdfjs;
if (require.main === module) {
    syncPdfjs(path.join(__dirname, '..', 'assets', 'pdfjs'));
}
