import { describe, it } from 'node:test';
import assert from 'node:assert';
import { calculatePdfChunks, formatPageInfo, sanitizePdfUri, getCompositeImageFilename, calculateExportScale } from './pdfHelpers.ts';

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
});
