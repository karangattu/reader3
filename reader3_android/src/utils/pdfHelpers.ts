export function calculatePdfChunks(totalLength: number, chunkSize: number): number {
    if (totalLength <= 0 || chunkSize <= 0) return 0;
    return Math.ceil(totalLength / chunkSize);
}

export function formatPageInfo(current: number, total: number): string {
    if (total <= 0) return 'Loading...';
    return `${current} / ${total}`;
}

export function sanitizePdfUri(uri: string): string {
    if (!uri) return '';
    if (uri.startsWith('file://')) return uri;
    if (uri.startsWith('/')) return `file://${uri}`;
    return uri;
}

export function getCompositeImageFilename(pages: number[], timestamp: number = Date.now()): string {
    if (!pages || pages.length === 0) return `composite_${timestamp}.png`;
    if (pages.length === 1) return `page_${pages[0]}_${timestamp}.png`;
    return `pages_${pages[0]}_to_${pages[pages.length - 1]}_${timestamp}.png`;
}

export function calculateExportScale(
    pageWidth: number,
    pageHeight: number,
    targetDpi: number = 300,
    maxDimension: number = 4096,
    maxPixels: number = 16777216
): number {
    if (pageWidth <= 0 || pageHeight <= 0) return 1.0;
    const baseScale = targetDpi / 72;
    const dimensionScale = maxDimension / Math.max(pageWidth, pageHeight);
    const areaScale = Math.sqrt(maxPixels / (pageWidth * pageHeight));
    return Math.min(baseScale, dimensionScale, areaScale);
}

export interface PdfPageDimensions {
    width: number;
    height: number;
}

export interface PdfCompositeLayout {
    scale: number;
    width: number;
    height: number;
    effectiveDpi: number;
    padding: number;
}

/**
 * Calculates a scale for a vertical page composite that fits within the
 * browser/WebView canvas limits. Returns null when the selection would be so
 * tall that the effective resolution drops below minDpi.
 *
 * Keep this algorithm in sync with calculatePdfCompositeLayout in
 * templates/reader.html.
 */
export function calculateCompositeLayout(
    pages: PdfPageDimensions[],
    targetDpi: number = 300,
    padding: number = 20,
    maxDimension: number = 16384,
    maxArea: number = 268435456,
    minDpi: number = 96
): PdfCompositeLayout | null {
    if (!pages || pages.length === 0) return null;

    const dimensions = pages.map((page) => ({
        width: page.width > 0 ? page.width : 612,
        height: page.height > 0 ? page.height : 792,
    }));
    const maxWidth = Math.max(...dimensions.map((page) => page.width));
    const totalHeight = dimensions.reduce((sum, page) => sum + page.height, 0);
    if (maxWidth <= 0 || totalHeight <= 0) return null;

    const paddingTotal = padding * Math.max(dimensions.length - 1, 0);
    let scale = targetDpi / 72;
    scale = Math.min(
        scale,
        maxDimension / maxWidth,
        Math.max(0, maxDimension - paddingTotal) / totalHeight
    );
    if (!Number.isFinite(scale) || scale <= 0) return null;

    let width = maxWidth * scale;
    let height = totalHeight * scale + paddingTotal;
    if (width * height > maxArea) {
        const a = maxWidth * totalHeight;
        const b = maxWidth * paddingTotal;
        const c = -maxArea;
        const discriminant = b * b - 4 * a * c;
        if (a <= 0 || discriminant <= 0) return null;
        scale = (-b + Math.sqrt(discriminant)) / (2 * a);
        width = maxWidth * scale;
        height = totalHeight * scale + paddingTotal;
    }

    const effectiveDpi = scale * 72;
    const finalWidth = Math.round(width);
    const finalHeight = Math.round(height);
    if (
        !Number.isFinite(effectiveDpi)
        || effectiveDpi < minDpi
        || finalWidth <= 0
        || finalHeight <= 0
        || finalWidth > maxDimension
        || finalHeight > maxDimension
    ) {
        return null;
    }

    return {
        scale,
        width: finalWidth,
        height: finalHeight,
        effectiveDpi,
        padding,
    };
}
