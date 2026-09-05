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
    maxDimension: number = 4096
): number {
    if (pageWidth <= 0 || pageHeight <= 0) return 1.0;
    const baseScale = targetDpi / 72;
    const targetWidth = pageWidth * baseScale;
    const targetHeight = pageHeight * baseScale;
    const largestDim = Math.max(targetWidth, targetHeight);
    if (largestDim > maxDimension) {
        return (maxDimension / Math.max(pageWidth, pageHeight));
    }
    return Math.max(baseScale, 1.0);
}
