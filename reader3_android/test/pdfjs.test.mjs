import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const require = createRequire(import.meta.url);
const syncPdfjs = require('../scripts/sync-pdfjs.cjs');

test('bundled PDF.js and its worker extract book text offline', async () => {
    const directory = mkdtempSync(join(tmpdir(), 'reader3-pdfjs-'));
    try {
        syncPdfjs(directory);
        const pdfjs = await import(pathToFileURL(join(directory, 'pdf.min.mjs')).href);
        const { version } = require('pdfjs-dist/package.json');
        assert.equal(pdfjs.version, version);
        const vm = require('node:vm');
        const legacyContext = vm.createContext();
        vm.runInContext('Promise.withResolvers = undefined', legacyContext);
        vm.runInContext(readFileSync(join(directory, 'polyfills.js'), 'utf8'), legacyContext);
        assert.equal(vm.runInContext('typeof Promise.withResolvers', legacyContext), 'function');
        assert.equal(vm.runInContext('typeof ReadableStream.prototype[Symbol.asyncIterator]', legacyContext), 'function');
        pdfjs.GlobalWorkerOptions.workerSrc = pathToFileURL(join(directory, 'pdf.worker.bootstrap.mjs')).href;
        const loading = pdfjs.getDocument({
            data: new Uint8Array(readFileSync(new URL('./fixtures/copy.pdf', import.meta.url))),
            isEvalSupported: false,
            useSystemFonts: true,
        });
        const doc = await loading.promise;
        try {
            assert.equal(doc.numPages, 1);
            const page = await doc.getPage(1);
            const content = await page.getTextContent();
            assert.equal(content.items.map(item => item.str).join(''), 'Reader3 offline copy test');
        } finally {
            await loading.destroy();
        }
    } finally {
        rmSync(directory, { recursive: true, force: true });
    }
});

// Evaluate the actual TSX templates first: raw source inspection misses escapes
// that become literal newlines when React Native creates the WebView HTML.
for (const [screen, variable] of [
    ['PDFReaderScreen', 'getPdfViewerHTML'],
    ['LibraryScreen', 'PDF_COVER_EXTRACTOR_HTML'],
]) {
    test(`${screen} produces valid inline JavaScript`, async () => {
        const ts = require('typescript');
        const vm = require('node:vm');
        const { PDFJS_BOOTSTRAP, PDFJS_DOCUMENT_OPTIONS } = await import('../src/utils/pdfjsBootstrap.ts');
        const { sanitizePdfUri } = await import('../src/utils/pdfHelpers.ts');
        const source = readFileSync(new URL(`../src/screens/${screen}.tsx`, import.meta.url), 'utf8');
        const file = ts.createSourceFile('screen.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
        let expression;
        function visit(node) {
            if (ts.isVariableDeclaration(node) && node.name.getText(file) === variable) {
                expression = node.initializer.getText(file);
            }
            ts.forEachChild(node, visit);
        }
        visit(file);
        assert.ok(expression, `Missing ${variable}`);
        const html = vm.runInNewContext(
            variable === 'getPdfViewerHTML' ? `(${expression})()` : expression,
            { book: { uri: 'file:///books/copy.pdf' }, insets: { bottom: 0 }, sanitizePdfUri, PDFJS_BOOTSTRAP, PDFJS_DOCUMENT_OPTIONS },
        );
        const scripts = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)];
        assert.ok(scripts.length >= 2);
        for (const [, script] of scripts) new vm.Script(script);
    });
}
