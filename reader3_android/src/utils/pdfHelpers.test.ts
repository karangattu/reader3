import { describe, it } from 'node:test';
import assert from 'node:assert';
import {
    calculatePdfChunks,
    formatPageInfo,
    sanitizePdfUri,
    getCompositeImageFilename,
    calculateExportScale,
    calculateCompositeLayout,
} from './pdfHelpers.ts';

describe('pdfHelpers', () => {
    it('calculates chunks correctly for varying data sizes', () => {
        assert.strictEqual(calculatePdfChunks(1000, 256), 4);
        assert.strictEqual(calculatePdfChunks(256, 256), 1);
        assert.strictEqual(calculatePdfChunks(0, 256), 0);
        assert.strictEqual(calculatePdfChunks(30 * 1024 * 1024, 256 * 1024), 120);
    });

    it('formats page info for loading and loaded states', () => {
        assert.strictEqual(formatPageInfo(1, 0), 'Loading...');
        assert.strictEqual(formatPageInfo(5, 50), '5 / 50');
    });

    it('sanitizes file URIs for Android WebView consumption', () => {
        assert.strictEqual(sanitizePdfUri('file:///data/user/0/app/books/test.pdf'), 'file:///data/user/0/app/books/test.pdf');
        assert.strictEqual(sanitizePdfUri('/data/user/0/app/books/test.pdf'), 'file:///data/user/0/app/books/test.pdf');
        assert.strictEqual(sanitizePdfUri(''), '');
    });

    it('generates safe composite image filenames', () => {
        assert.strictEqual(getCompositeImageFilename([1], 12345), 'page_1_12345.png');
        assert.strictEqual(getCompositeImageFilename([1, 2, 3, 4, 5], 12345), 'pages_1_to_5_12345.png');
        assert.strictEqual(getCompositeImageFilename([], 12345), 'composite_12345.png');
    });

    it('calculates export scale accurately with DPI scaling and dimension caps', () => {
        const standardScale = calculateExportScale(595, 842, 300, 4096);
        assert.strictEqual(standardScale, 300 / 72);

        const cappedScale = calculateExportScale(2000, 3000, 300, 4096);
        assert.strictEqual(cappedScale, 4096 / 3000);

        assert.strictEqual(calculateExportScale(0, 842), 1.0);
        assert.strictEqual(calculateExportScale(595, 0), 1.0);
    });

    it('caps high-resolution exports by total pixels', () => {
        const scale = calculateExportScale(5000, 5000, 300, 4096, 16777216);
        assert.strictEqual(scale, Math.sqrt(16777216 / (5000 * 5000)));
    });

    it('fits a small page selection into one composite at the target DPI', () => {
        const pages = Array.from({ length: 4 }, () => ({ width: 595, height: 842 }));
        const layout = calculateCompositeLayout(pages, 300, 20, 16384, 268435456, 96);

        assert.ok(layout);
        assert.strictEqual(layout.effectiveDpi, 300);
        assert.ok(layout.height <= 16384);
        assert.ok(layout.width <= 16384);
    });

    it('reduces DPI for medium selections so they still fit', () => {
        const pages = Array.from({ length: 10 }, () => ({ width: 595, height: 842 }));
        const layout = calculateCompositeLayout(pages, 300, 20, 16384, 268435456, 96);

        assert.ok(layout);
        assert.ok(layout.effectiveDpi < 300);
        assert.ok(layout.effectiveDpi >= 96);
        assert.ok(layout.height <= 16384);
    });

    it('rejects selections that would be unreadably small', () => {
        const pages = Array.from({ length: 20 }, () => ({ width: 595, height: 842 }));
        assert.strictEqual(calculateCompositeLayout(pages, 300, 20, 16384, 268435456, 96), null);
    });

    it('honors the composite area cap', () => {
        const pages = Array.from({ length: 3 }, () => ({ width: 4000, height: 1000 }));
        const layout = calculateCompositeLayout(pages, 300, 20, 16384, 1000000, 1);

        assert.ok(layout);
        assert.ok(layout.width * layout.height <= 1000000);
    });
});
