import React, { useState, useRef, useCallback, useEffect } from "react";
import {
    View, StyleSheet, TouchableOpacity, Text,
    ScrollView, Modal, TextInput, Alert,
} from "react-native";
import { WebView, WebViewMessageEvent } from "react-native-webview";
import * as Clipboard from "expo-clipboard";
import * as Sharing from "expo-sharing";
import * as FileSystem from "expo-file-system";
import { Directory, File as ExpoFile } from "expo-file-system";
import { useRoute, useNavigation } from "@react-navigation/native";
import { BookEntry } from "./LibraryScreen";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FontAwesome from "@expo/vector-icons/FontAwesome";
import { formatPageInfo, calculatePdfChunks, sanitizePdfUri, getCompositeImageFilename } from "../utils/pdfHelpers.ts";

export default function PDFReaderScreen() {
    const route = useRoute<any>();
    const navigation = useNavigation<any>();
    const book = route.params?.book as BookEntry;
    const webviewRef = useRef<WebView>(null);
    const insets = useSafeAreaInsets();

    const [totalPages, setTotalPages] = useState(0);
    const [currentPage, setCurrentPage] = useState(1);
    const [jumpModalVisible, setJumpModalVisible] = useState(false);
    const [jumpPageText, setJumpPageText] = useState("");
    const [toastMessage, setToastMessage] = useState<string | null>(null);
    const [outlineVisible, setOutlineVisible] = useState(false);
    const [outline, setOutline] = useState<{ title: string; page: number }[]>([]);

    const showToast = useCallback((msg: string) => {
        setToastMessage(msg);
        setTimeout(() => setToastMessage(null), 2500);
    }, []);

    const loadProgress = useCallback(async () => {
        if (!book?.id) return;
        try {
            const data = await AsyncStorage.getItem(`@reader3:pdf-progress:${book.id}`);
            if (data) {
                const parsed = JSON.parse(data);
                if (parsed.lastPage) setCurrentPage(parsed.lastPage);
            }
        } catch { }
    }, [book?.id]);

    const saveProgress = useCallback(async (page: number) => {
        if (!book?.id) return;
        try {
            await AsyncStorage.setItem(`@reader3:pdf-progress:${book.id}`, JSON.stringify({
                lastPage: page,
                totalPages,
            }));
        } catch { }
    }, [book?.id, totalPages]);

    useEffect(() => {
        if (book?.uri) {
            loadProgress();
        }
    }, [book?.uri, loadProgress]);

    const sendPdfChunks = useCallback(async () => {
        if (!book?.uri) return;
        try {
            const file = new ExpoFile(book.uri);
            const base64Data = await file.base64();
            const chunkSize = 256 * 1024;
            const total = calculatePdfChunks(base64Data.length, chunkSize);
            for (let i = 0; i < total; i++) {
                const chunk = base64Data.substring(i * chunkSize, (i + 1) * chunkSize);
                webviewRef.current?.injectJavaScript(`
                    if (window.receivePdfChunk) {
                        window.receivePdfChunk(${i}, ${total}, ${JSON.stringify(chunk)});
                    }
                    true;
                `);
            }
        } catch (err: any) {
            webviewRef.current?.injectJavaScript(`
                if (window.handlePdfError) {
                    window.handlePdfError(${JSON.stringify(err?.message || "Failed to read PDF file")});
                }
                true;
            `);
        }
    }, [book?.uri]);

    const savePdfPageImage = useCallback(async (dataUrl: string, page: number) => {
        const base64 = dataUrl.replace(/^data:image\/png;base64,/, "");
        let copiedToClipboard = false;
        try {
            await Clipboard.setImageAsync(base64);
            copiedToClipboard = true;
        } catch { }

        let savedFilePath: string | null = null;
        try {
            const cacheDir = new Directory(FileSystem.Paths.cache, "reader3_images");
            if (!cacheDir.exists) cacheDir.create();

            const filename = `page_${page}_${Date.now()}.png`;
            const imgFile = new ExpoFile(cacheDir, filename);
            if (!imgFile.exists) {
                imgFile.create({ overwrite: true });
            }
            imgFile.write(base64, { encoding: "base64" });
            savedFilePath = imgFile.uri;
        } catch { }

        if (copiedToClipboard) {
            showToast(`Page ${page} image copied to clipboard!`);
        } else if (savedFilePath) {
            showToast(`Page ${page} image saved`);
        } else {
            showToast("Failed to save image");
        }

        if (savedFilePath) {
            try {
                if (await Sharing.isAvailableAsync()) {
                    await Sharing.shareAsync(savedFilePath, {
                        mimeType: "image/png",
                        dialogTitle: `Page ${page} - ${book?.title || "PDF"}`,
                    });
                }
            } catch { }
        }
    }, [book?.title, showToast]);

    const savePdfCompositeImage = useCallback(async (dataUrl: string, pages: number[]) => {
        const base64 = dataUrl.replace(/^data:image\/png;base64,/, "");
        let copiedToClipboard = false;
        try {
            await Clipboard.setImageAsync(base64);
            copiedToClipboard = true;
        } catch { }

        let savedFilePath: string | null = null;
        try {
            const cacheDir = new Directory(FileSystem.Paths.cache, "reader3_images");
            if (!cacheDir.exists) cacheDir.create();

            const filename = getCompositeImageFilename(pages);
            const imgFile = new ExpoFile(cacheDir, filename);
            if (!imgFile.exists) {
                imgFile.create({ overwrite: true });
            }
            imgFile.write(base64, { encoding: "base64" });
            savedFilePath = imgFile.uri;
        } catch { }

        if (copiedToClipboard) {
            showToast(`${pages.length} page${pages.length > 1 ? "s" : ""} image copied to clipboard!`);
        } else if (savedFilePath) {
            showToast(`${pages.length} page${pages.length > 1 ? "s" : ""} composite image saved`);
        } else {
            showToast("Failed to save composite image");
        }

        if (savedFilePath) {
            try {
                if (await Sharing.isAvailableAsync()) {
                    await Sharing.shareAsync(savedFilePath, {
                        mimeType: "image/png",
                        dialogTitle: `Pages ${pages.join(", ")} - ${book?.title || "PDF"}`,
                    });
                }
            } catch { }
        }
    }, [book?.title, showToast]);

    const savePdfCover = useCallback(async (bookId: string, dataUrl: string) => {
        try {
            const base64 = dataUrl.replace(/^data:image\/[a-z]+;base64,/, "");
            const coversDir = new Directory(FileSystem.Paths.document, "covers");
            if (!coversDir.exists) coversDir.create();
            const coverFile = new ExpoFile(coversDir, `${bookId}_cover.jpg`);
            if (!coverFile.exists) coverFile.create({ overwrite: true });
            coverFile.write(base64, { encoding: "base64" });

            const stored = await AsyncStorage.getItem("@reader3:books");
            if (stored) {
                const books: BookEntry[] = JSON.parse(stored);
                const idx = books.findIndex(b => b.id === bookId);
                if (idx >= 0 && !books[idx].coverUri) {
                    books[idx].coverUri = coverFile.uri;
                    await AsyncStorage.setItem("@reader3:books", JSON.stringify(books));
                }
            }
        } catch { }
    }, []);

    const onWebViewMessage = useCallback((event: WebViewMessageEvent) => {
        try {
            const data = JSON.parse(event.nativeEvent.data);
            switch (data.type) {
                case "pdfLoaded":
                    setTotalPages(data.totalPages);
                    if (data.outline) setOutline(data.outline);
                    break;
                case "requestChunks":
                    sendPdfChunks();
                    break;
                case "pageChanged":
                    setCurrentPage(data.page);
                    saveProgress(data.page);
                    break;
                case "page1Rendered":
                    if (book?.id) savePdfCover(book.id, data.dataUrl);
                    break;
                case "copyText":
                    Clipboard.setStringAsync(data.text);
                    showToast(`Page text copied (${data.text.length} chars)`);
                    break;
                case "copyImage":
                    savePdfPageImage(data.dataUrl, data.page);
                    break;
                case "copySelectedImages":
                    savePdfCompositeImage(data.dataUrl, data.pages);
                    break;
                case "selectionCopy":
                    Clipboard.setStringAsync(data.text);
                    showToast("Text copied!");
                    break;
                case "error":
                    Alert.alert("PDF Error", data.message);
                    break;
            }
        } catch { }
    }, [saveProgress, savePdfPageImage, savePdfCompositeImage, savePdfCover, sendPdfChunks, book?.id, showToast]);

    const sendCommand = (cmd: string, args: any = {}) => {
        webviewRef.current?.injectJavaScript(`
            if (window.handleCommand) {
                window.handleCommand(${JSON.stringify({ cmd, ...args })});
            }
            true;
        `);
    };

    const copyCurrentPageText = () => sendCommand("copyPageText", { page: currentPage });
    const copyCurrentPageImage = () => sendCommand("copyPageImage", { page: currentPage });

    const jumpToPage = () => {
        const page = parseInt(jumpPageText, 10);
        if (page >= 1 && page <= totalPages) {
            sendCommand("goToPage", { page });
            setCurrentPage(page);
            setJumpModalVisible(false);
            setJumpPageText("");
        } else {
            Alert.alert("Invalid Page", `Enter a page between 1 and ${totalPages}`);
        }
    };

    const getPdfViewerHTML = () => `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<script src="file:///android_asset/pdfjs/pdf.min.js"></script>
<script>
if (typeof pdfjsLib === "undefined") {
    document.write('<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"><\/script>');
}
</script>
<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { background: #525659; font-family: -apple-system, sans-serif; padding-bottom: 70px; }
    .page-container {
        margin: 10px auto;
        background: white;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        position: relative;
        overflow: hidden;
        min-height: 200px;
    }
    .page-header {
        position: sticky;
        top: 0;
        background: rgba(255,255,255,0.95);
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 8px 12px;
        border-bottom: 1px solid #eee;
        z-index: 10;
        font-size: 13px;
    }
    .page-header-left {
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .page-header .page-num { font-weight: 600; color: #333; font-size: 14px; }
    .copied-badge {
        display: none;
        background: #27ae60;
        color: #fff;
        font-size: 10px;
        font-weight: 700;
        padding: 2px 6px;
        border-radius: 4px;
    }
    .copied-badge.visible { display: inline-block; }
    .page-actions { display: flex; gap: 6px; }
    .page-actions button {
        background: #007AFF;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 12px;
        font-weight: 600;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        gap: 4px;
    }
    .page-actions button.text-btn { background: #34C759; }
    canvas { display: block; width: 100%; height: auto; }
    .page-placeholder {
        height: 400px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #888;
        font-size: 14px;
    }
    .page-select-check {
        width: 22px; height: 22px;
        border: 2px solid #007AFF;
        border-radius: 4px;
        appearance: none;
        -webkit-appearance: none;
        cursor: pointer;
        position: relative;
    }
    .page-select-check:checked {
        background-color: #007AFF;
        background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14' fill='white' viewBox='0 0 16 16'%3E%3Cpath d='M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z'/%3E%3C/svg%3E");
        background-repeat: no-repeat;
        background-position: center;
    }
    #loading-indicator {
        position: fixed;
        top: 50%; left: 50%;
        transform: translate(-50%, -50%);
        background: rgba(0,0,0,0.85);
        color: white;
        padding: 20px 30px;
        border-radius: 12px;
        font-size: 16px;
        z-index: 999;
        text-align: center;
    }
    #select-bar {
        position: fixed;
        bottom: 0;
        left: 0; right: 0;
        background: #1c1c1e;
        color: white;
        padding: 10px 16px 26px 16px;
        display: none;
        align-items: center;
        justify-content: space-between;
        z-index: 100;
        border-top: 1px solid #333;
    }
    #select-bar.visible { display: flex; }
    .select-bar-actions { display: flex; gap: 8px; align-items: center; }
    .select-bar-btn {
        background: #007AFF;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 8px 14px;
        font-weight: 700;
        font-size: 13px;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        gap: 4px;
    }
    .select-bar-btn.secondary {
        background: #333;
        color: #eee;
        font-weight: 500;
    }
</style>
</head>
<body>
<div id="loading-indicator">Loading PDF...</div>
<div id="pdf-container"></div>
<div id="select-bar" style="padding-bottom: ${Math.max(insets.bottom + 10, 20)}px;">
    <span id="select-count">0 pages selected</span>
    <div class="select-bar-actions">
        <button class="select-bar-btn secondary" onclick="selectAllPages()">
            <svg width="13" height="13" fill="currentColor" viewBox="0 0 16 16"><path d="M2.5 3.5a.5.5 0 0 1 0-1h11a.5.5 0 0 1 0 1h-11zm0 3a.5.5 0 0 1 0-1h11a.5.5 0 0 1 0 1h-11zm0 3a.5.5 0 0 1 0-1h11a.5.5 0 0 1 0 1h-11zm0 3a.5.5 0 0 1 0-1h11a.5.5 0 0 1 0 1h-11z"/></svg>
            Select All
        </button>
        <button class="select-bar-btn secondary" onclick="clearSelectedPages()">
            <svg width="13" height="13" fill="currentColor" viewBox="0 0 16 16"><path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/></svg>
            Clear
        </button>
        <button class="select-bar-btn" onclick="copySelectedPagesAsImage()">
            <svg width="13" height="13" fill="currentColor" viewBox="0 0 16 16"><path d="M4 1.5H3a2 2 0 0 0-2 2V14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V3.5a2 2 0 0 0-2-2h-1v1h1a1 1 0 0 1 1 1V14a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1h1v-1z"/><path d="M9.5 1a.5.5 0 0 1 .5.5v1a.5.5 0 0 1-.5.5h-3a.5.5 0 0 1-.5-.5v-1a.5.5 0 0 1 .5-.5h3zm-3-1A1.5 1.5 0 0 0 5 1.5v1A1.5 1.5 0 0 0 6.5 4h3A1.5 1.5 0 0 0 11 2.5v-1A1.5 1.5 0 0 0 9.5 0h-3z"/></svg>
            Copy Images
        </button>
    </div>
</div>

<script>
    if (window.pdfjsLib) {
        pdfjsLib.GlobalWorkerOptions.workerSrc = "file:///android_asset/pdfjs/pdf.worker.min.js";
    }

    var PDF_FILE_URI = ${JSON.stringify(sanitizePdfUri(book?.uri || ""))};
    var pdfDoc = null;
    var pageCanvases = {};
    var pageTexts = {};
    var selectedPages = new Set();
    var renderingPages = {};
    var receivedChunks = [];
    var totalExpectedChunks = 0;

    window.receivePdfChunk = function(index, total, chunk) {
        receivedChunks[index] = chunk;
        totalExpectedChunks = total;
        var count = Object.keys(receivedChunks).length;
        var indicator = document.getElementById("loading-indicator");
        if (indicator) indicator.textContent = "Loading PDF (" + Math.round((count / total) * 100) + "%)...";

        if (count === total) {
            var fullBase64 = receivedChunks.join("");
            var binary = atob(fullBase64);
            var len = binary.length;
            var bytes = new Uint8Array(len);
            for (var i = 0; i < len; i++) {
                bytes[i] = binary.charCodeAt(i);
            }
            initPdfWithData(bytes);
        }
    };

    window.handlePdfError = function(msg) {
        var indicator = document.getElementById("loading-indicator");
        if (indicator) indicator.textContent = "Error: " + msg;
        window.ReactNativeWebView.postMessage(JSON.stringify({
            type: "error",
            message: msg,
        }));
    };

    function loadPdfArrayBuffer(uri) {
        return new Promise(function(resolve, reject) {
            var xhr = new XMLHttpRequest();
            xhr.open("GET", uri, true);
            xhr.responseType = "arraybuffer";
            xhr.onload = function() {
                if (xhr.status === 200 || xhr.status === 0) {
                    if (xhr.response && xhr.response.byteLength > 0) {
                        resolve(new Uint8Array(xhr.response));
                    } else {
                        reject(new Error("Empty PDF file"));
                    }
                } else {
                    reject(new Error("XHR status: " + xhr.status));
                }
            };
            xhr.onerror = function() {
                reject(new Error("XHR file read failed"));
            };
            xhr.send();
        });
    }

    async function initPdfWithData(uint8) {
        try {
            if (!window.pdfjsLib) throw new Error("PDF.js library failed to load");
            pdfDoc = await pdfjsLib.getDocument({ data: uint8 }).promise;
            var totalPages = pdfDoc.numPages;

            var outlineData = [];
            try {
                var outline = await pdfDoc.getOutline();
                if (outline) {
                    for (var k = 0; k < outline.length; k++) {
                        var item = outline[k];
                        try {
                            var dest = await pdfDoc.getDestination(item.dest || item.url);
                            if (dest) {
                                var pageIdx = await pdfDoc.getPageIndex(dest[0]);
                                outlineData.push({ title: item.title, page: pageIdx + 1 });
                            }
                        } catch(e) {
                            outlineData.push({ title: item.title, page: 1 });
                        }
                    }
                }
            } catch(e) {}

            window.ReactNativeWebView.postMessage(JSON.stringify({
                type: "pdfLoaded",
                totalPages: totalPages,
                outline: outlineData,
            }));

            var indicator = document.getElementById("loading-indicator");
            if (indicator) indicator.style.display = "none";

            var container = document.getElementById("pdf-container");
            for (var i = 1; i <= totalPages; i++) {
                createPagePlaceholder(i, container);
            }

            var initialRender = Math.min(totalPages, 3);
            for (var j = 1; j <= initialRender; j++) {
                renderPage(j);
            }
        } catch(err) {
            window.handlePdfError("Failed to parse PDF: " + (err.message || String(err)));
        }
    }

    async function startLoad() {
        if (!PDF_FILE_URI) {
            window.handlePdfError("No PDF URI provided");
            return;
        }
        try {
            var uint8 = await loadPdfArrayBuffer(PDF_FILE_URI);
            await initPdfWithData(uint8);
        } catch(err) {
            window.ReactNativeWebView.postMessage(JSON.stringify({ type: "requestChunks" }));
        }
    }

    function createPagePlaceholder(pageNum, container) {
        var pageDiv = document.createElement("div");
        pageDiv.className = "page-container";
        pageDiv.id = "page-" + pageNum;
        pageDiv.dataset.page = pageNum;

        pageDiv.innerHTML = '<div class="page-header">' +
            '<div class="page-header-left">' +
            '<input type="checkbox" class="page-select-check" data-page="' + pageNum + '" onchange="toggleSelect(' + pageNum + ', this.checked)" />' +
            '<span class="page-num">Page ' + pageNum + '</span>' +
            '<span class="copied-badge" id="badge-' + pageNum + '">Copied</span>' +
            '</div>' +
            '<div class="page-actions">' +
            '<button class="text-btn" onclick="copyPageText(' + pageNum + ')">' +
            '<svg width="12" height="12" fill="currentColor" viewBox="0 0 16 16"><path d="M4 0h8a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V2a2 2 0 0 1 2-2zm0 1a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V2a1 1 0 0 0-1-1H4z"/><path d="M4.5 10.5A.5.5 0 0 1 5 10h6a.5.5 0 0 1 0 1H5a.5.5 0 0 1-.5-.5zm0-2A.5.5 0 0 1 5 8h6a.5.5 0 0 1 0 1H5a.5.5 0 0 1-.5-.5zm0-2A.5.5 0 0 1 5 6h6a.5.5 0 0 1 0 1H5a.5.5 0 0 1-.5-.5zm0-2A.5.5 0 0 1 5 4h6a.5.5 0 0 1 0 1H5a.5.5 0 0 1-.5-.5z"/></svg>' +
            'Copy Text</button>' +
            '<button onclick="copyPageImage(' + pageNum + ')">' +
            '<svg width="12" height="12" fill="currentColor" viewBox="0 0 16 16"><path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/><path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/></svg>' +
            'Copy Image</button>' +
            '</div></div>' +
            '<div class="page-placeholder" id="placeholder-' + pageNum + '">Loading page ' + pageNum + '...</div>';

        container.appendChild(pageDiv);

        var observer = new IntersectionObserver(function(entries) {
            entries.forEach(function(entry) {
                if (entry.isIntersecting) {
                    renderPage(pageNum);
                    window.ReactNativeWebView.postMessage(JSON.stringify({
                        type: "pageChanged",
                        page: pageNum,
                    }));
                }
            });
        }, { rootMargin: "300px 0px" });

        observer.observe(pageDiv);
    }

    async function renderPage(pageNum) {
        if (pageCanvases[pageNum] || renderingPages[pageNum] || !pdfDoc) return;
        renderingPages[pageNum] = true;

        try {
            var page = await pdfDoc.getPage(pageNum);
            var container = document.getElementById("page-" + pageNum);
            var containerWidth = container.clientWidth || window.innerWidth;
            var unscaledViewport = page.getViewport({ scale: 1.0 });
            var targetScale = (containerWidth / unscaledViewport.width) * (window.devicePixelRatio || 2);
            var viewport = page.getViewport({ scale: Math.max(targetScale, 1.5) });

            var canvas = document.createElement("canvas");
            canvas.width = viewport.width;
            canvas.height = viewport.height;
            canvas.style.width = "100%";
            canvas.style.height = "auto";

            var ctx = canvas.getContext("2d");
            await page.render({ canvasContext: ctx, viewport: viewport }).promise;

            pageCanvases[pageNum] = canvas;

            var textContent = await page.getTextContent();
            var text = textContent.items.map(function(item) { return item.str; }).join(" ");
            pageTexts[pageNum] = text;

            var placeholder = document.getElementById("placeholder-" + pageNum);
            if (placeholder) placeholder.replaceWith(canvas);

            if (pageNum === 1) {
                var coverScale = 240 / unscaledViewport.width;
                var coverVp = page.getViewport({ scale: Math.max(coverScale, 0.4) });
                var coverCanvas = document.createElement("canvas");
                coverCanvas.width = coverVp.width;
                coverCanvas.height = coverVp.height;
                var coverCtx = coverCanvas.getContext("2d");
                await page.render({ canvasContext: coverCtx, viewport: coverVp }).promise;
                var coverDataUrl = coverCanvas.toDataURL("image/jpeg", 0.85);
                window.ReactNativeWebView.postMessage(JSON.stringify({
                    type: "page1Rendered",
                    dataUrl: coverDataUrl,
                }));
            }
        } catch(err) {
            console.error("Error rendering page " + pageNum, err);
        } finally {
            delete renderingPages[pageNum];
        }
    }

    async function renderHighResPage(pageNum, targetDpi = 300) {
        if (!pdfDoc) return null;
        var page = await pdfDoc.getPage(pageNum);
        var unscaledViewport = page.getViewport({ scale: 1.0 });
        var baseScale = targetDpi / 72;
        var maxDimension = 4096;
        var largestDim = Math.max(unscaledViewport.width * baseScale, unscaledViewport.height * baseScale);
        var scale = largestDim > maxDimension ? (maxDimension / Math.max(unscaledViewport.width, unscaledViewport.height)) : Math.max(baseScale, 1.0);
        var viewport = page.getViewport({ scale: scale });

        var canvas = document.createElement("canvas");
        canvas.width = Math.floor(viewport.width);
        canvas.height = Math.floor(viewport.height);
        var ctx = canvas.getContext("2d");
        await page.render({ canvasContext: ctx, viewport: viewport }).promise;
        return canvas;
    }

    window.handleCommand = function(data) {
        switch (data.cmd) {
            case "goToPage":
                var el = document.getElementById("page-" + data.page);
                if (el) el.scrollIntoView({ behavior: "smooth" });
                break;
            case "copyPageText":
                copyPageText(data.page);
                break;
            case "copyPageImage":
                copyPageImage(data.page);
                break;
        }
    };

    window.copyPageText = async function(pageNum) {
        if (!pageTexts[pageNum]) await renderPage(pageNum);
        var text = pageTexts[pageNum] || "";
        window.ReactNativeWebView.postMessage(JSON.stringify({
            type: "copyText",
            page: pageNum,
            text: text,
        }));
        var badge = document.getElementById("badge-" + pageNum);
        if (badge) badge.classList.add("visible");
    };

    window.copyPageImage = async function(pageNum) {
        try {
            var canvas = await renderHighResPage(pageNum, 300);
            if (!canvas) {
                if (!pageCanvases[pageNum]) await renderPage(pageNum);
                canvas = pageCanvases[pageNum];
            }
            if (!canvas) return;
            var dataUrl = canvas.toDataURL("image/png");
            window.ReactNativeWebView.postMessage(JSON.stringify({
                type: "copyImage",
                page: pageNum,
                dataUrl: dataUrl,
            }));
            var badge = document.getElementById("badge-" + pageNum);
            if (badge) badge.classList.add("visible");
        } catch(err) {
            console.error("Failed to export high-res page image", err);
        }
    };

    window.toggleSelect = function(pageNum, checked) {
        if (checked) selectedPages.add(pageNum);
        else selectedPages.delete(pageNum);
        updateSelectBar();
    };

    window.selectAllPages = function() {
        if (!pdfDoc) return;
        for (var i = 1; i <= pdfDoc.numPages; i++) {
            selectedPages.add(i);
            var check = document.querySelector('input[data-page="' + i + '"]');
            if (check) check.checked = true;
        }
        updateSelectBar();
    };

    window.clearSelectedPages = function() {
        selectedPages.clear();
        document.querySelectorAll(".page-select-check").forEach(function(c) { c.checked = false; });
        updateSelectBar();
    };

    function updateSelectBar() {
        var bar = document.getElementById("select-bar");
        var count = document.getElementById("select-count");
        if (selectedPages.size > 0) {
            bar.classList.add("visible");
            count.textContent = selectedPages.size + " page" + (selectedPages.size > 1 ? "s" : "") + " selected";
        } else {
            bar.classList.remove("visible");
        }
    }

    window.copySelectedPagesAsImage = async function() {
        var pages = Array.from(selectedPages).sort(function(a, b) { return a - b; });
        if (pages.length === 0) return;

        try {
            var targetDpi = pages.length > 5 ? 200 : 300;
            var canvases = [];
            for (var i = 0; i < pages.length; i++) {
                var p = pages[i];
                var c = await renderHighResPage(p, targetDpi);
                if (!c) {
                    if (!pageCanvases[p]) await renderPage(p);
                    c = pageCanvases[p];
                }
                if (c) canvases.push(c);
            }

            if (canvases.length === 0) return;

            var padding = 20;
            var maxWidth = 0;
            var totalHeight = 0;
            for (var j = 0; j < canvases.length; j++) {
                if (canvases[j].width > maxWidth) maxWidth = canvases[j].width;
                totalHeight += canvases[j].height + padding;
            }

            var maxAllowedHeight = 16384;
            var scaleDown = totalHeight > maxAllowedHeight ? (maxAllowedHeight / totalHeight) : 1.0;
            var finalWidth = Math.floor(maxWidth * scaleDown);
            var finalHeight = Math.floor(totalHeight * scaleDown);

            var compositeCanvas = document.createElement("canvas");
            compositeCanvas.width = finalWidth;
            compositeCanvas.height = finalHeight;
            var ctx = compositeCanvas.getContext("2d");
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(0, 0, finalWidth, finalHeight);

            var yOffset = 0;
            for (var k = 0; k < canvases.length; k++) {
                var itemCanvas = canvases[k];
                var itemW = itemCanvas.width * scaleDown;
                var itemH = itemCanvas.height * scaleDown;
                var xOffset = (finalWidth - itemW) / 2;
                ctx.drawImage(itemCanvas, xOffset, yOffset, itemW, itemH);
                yOffset += itemH + (padding * scaleDown);
            }

            pages.forEach(function(p) {
                var badge = document.getElementById("badge-" + p);
                if (badge) badge.classList.add("visible");
            });

            var dataUrl = compositeCanvas.toDataURL("image/png");
            window.ReactNativeWebView.postMessage(JSON.stringify({
                type: "copySelectedImages",
                dataUrl: dataUrl,
                pages: pages,
            }));
        } catch(err) {
            console.error("Failed to export high-res composite image", err);
        }
    };

    startLoad();
</script>
</body>
</html>`;

    if (!book) {
        return (
            <View style={styles.errorContainer}>
                <Text style={styles.errorText}>No book provided</Text>
            </View>
        );
    }

    return (
        <View style={[styles.safeArea, { paddingTop: insets.top }]}>
            <View style={styles.header}>
                <TouchableOpacity style={styles.headerBtn} onPress={() => navigation.goBack()}>
                    <FontAwesome name="arrow-left" size={18} color="#007AFF" />
                </TouchableOpacity>
                <TouchableOpacity style={styles.titleArea} onPress={() => setJumpModalVisible(true)}>
                    <Text style={styles.title} numberOfLines={1}>{book.title}</Text>
                    <Text style={styles.pageInfo}>
                        {formatPageInfo(currentPage, totalPages)}
                    </Text>
                </TouchableOpacity>
                {outline.length > 0 && (
                    <TouchableOpacity style={styles.headerBtn} onPress={() => setOutlineVisible(true)}>
                        <FontAwesome name="bars" size={18} color="#007AFF" />
                    </TouchableOpacity>
                )}
            </View>

            <View style={styles.actionBar}>
                <TouchableOpacity style={styles.actionBtn} onPress={copyCurrentPageText}>
                    <View style={styles.actionBtnRow}>
                        <FontAwesome name="file-text-o" size={14} color="#007AFF" />
                        <Text style={styles.actionBtnText}>Copy Text</Text>
                    </View>
                </TouchableOpacity>
                <TouchableOpacity style={styles.actionBtn} onPress={copyCurrentPageImage}>
                    <View style={styles.actionBtnRow}>
                        <FontAwesome name="image" size={14} color="#007AFF" />
                        <Text style={styles.actionBtnText}>Copy Image</Text>
                    </View>
                </TouchableOpacity>
                <TouchableOpacity style={styles.actionBtn} onPress={() => setJumpModalVisible(true)}>
                    <View style={styles.actionBtnRow}>
                        <FontAwesome name="bookmark-o" size={14} color="#007AFF" />
                        <Text style={styles.actionBtnText}>Go to Page</Text>
                    </View>
                </TouchableOpacity>
            </View>

            <View style={styles.container}>
                <WebView
                    ref={webviewRef}
                    originWhitelist={["*"]}
                    source={{ html: getPdfViewerHTML(), baseUrl: "file:///" }}
                    style={styles.webview}
                    javaScriptEnabled={true}
                    onMessage={onWebViewMessage}
                    allowFileAccess={true}
                    allowFileAccessFromFileURLs={true}
                    allowUniversalAccessFromFileURLs={true}
                    allowingReadAccessToURL={book.uri}
                    mixedContentMode="always"
                    domStorageEnabled={true}
                />
            </View>

            <Modal visible={jumpModalVisible} transparent animationType="fade">
                <View style={styles.modalOverlay}>
                    <View style={styles.jumpModal}>
                        <Text style={styles.jumpTitle}>Go to Page</Text>
                        <TextInput
                            style={styles.jumpInput}
                            keyboardType="number-pad"
                            placeholder={`1 - ${totalPages}`}
                            value={jumpPageText}
                            onChangeText={setJumpPageText}
                            autoFocus
                            onSubmitEditing={jumpToPage}
                        />
                        <View style={styles.jumpButtons}>
                            <TouchableOpacity
                                style={styles.jumpCancel}
                                onPress={() => { setJumpModalVisible(false); setJumpPageText(""); }}
                            >
                                <Text style={styles.jumpCancelText}>Cancel</Text>
                            </TouchableOpacity>
                            <TouchableOpacity style={styles.jumpGo} onPress={jumpToPage}>
                                <Text style={styles.jumpGoText}>Go</Text>
                            </TouchableOpacity>
                        </View>
                    </View>
                </View>
            </Modal>

            <Modal visible={outlineVisible} animationType="slide" transparent>
                <View style={styles.modalOverlay}>
                    <View style={styles.outlinePanel}>
                        <View style={styles.outlineHeader}>
                            <Text style={styles.outlineTitle}>Outline</Text>
                            <TouchableOpacity onPress={() => setOutlineVisible(false)}>
                                <FontAwesome name="times" size={20} color="#666" />
                            </TouchableOpacity>
                        </View>
                        <ScrollView style={styles.outlineList}>
                            {outline.map((item, idx) => (
                                <TouchableOpacity
                                    key={idx}
                                    style={styles.outlineItem}
                                    onPress={() => {
                                        sendCommand("goToPage", { page: item.page });
                                        setCurrentPage(item.page);
                                        setOutlineVisible(false);
                                    }}
                                >
                                    <Text style={styles.outlineItemTitle} numberOfLines={2}>{item.title}</Text>
                                    <Text style={styles.outlineItemPage}>p. {item.page}</Text>
                                </TouchableOpacity>
                            ))}
                        </ScrollView>
                    </View>
                </View>
            </Modal>

            {toastMessage && (
                <View style={[styles.toast, { bottom: Math.max(insets.bottom + 20, 30) }]}>
                    <Text style={styles.toastText}>{toastMessage}</Text>
                </View>
            )}
        </View>
    );
}

const styles = StyleSheet.create({
    safeArea: {
        flex: 1,
        backgroundColor: "#f5f5f7",
    },
    header: {
        flexDirection: "row",
        alignItems: "center",
        paddingHorizontal: 12,
        paddingVertical: 8,
        backgroundColor: "#ffffff",
        borderBottomWidth: 1,
        borderBottomColor: "#e0e0e0",
    },
    headerBtn: {
        padding: 8,
        minWidth: 40,
        alignItems: "center",
    },
    titleArea: {
        flex: 1,
        alignItems: "center",
        paddingHorizontal: 8,
    },
    title: {
        fontSize: 16,
        fontWeight: "bold",
        color: "#333",
    },
    pageInfo: {
        fontSize: 12,
        color: "#666",
        marginTop: 2,
    },
    actionBar: {
        flexDirection: "row",
        justifyContent: "space-around",
        paddingVertical: 8,
        paddingHorizontal: 12,
        backgroundColor: "#ffffff",
        borderBottomWidth: 1,
        borderBottomColor: "#e0e0e0",
    },
    actionBtn: {
        paddingVertical: 6,
        paddingHorizontal: 14,
        borderRadius: 16,
        backgroundColor: "#eef2ff",
    },
    actionBtnRow: {
        flexDirection: "row",
        alignItems: "center",
        gap: 6,
    },
    actionBtnText: {
        fontSize: 12,
        fontWeight: "600",
        color: "#007AFF",
    },
    container: {
        flex: 1,
        backgroundColor: "#525659",
    },
    webview: {
        flex: 1,
        backgroundColor: "#525659",
    },
    errorContainer: {
        flex: 1,
        justifyContent: "center",
        alignItems: "center",
    },
    errorText: {
        color: "#ff3b30",
        fontSize: 16,
    },
    modalOverlay: {
        flex: 1,
        backgroundColor: "rgba(0,0,0,0.5)",
        justifyContent: "center",
        alignItems: "center",
    },
    jumpModal: {
        backgroundColor: "white",
        borderRadius: 16,
        padding: 20,
        width: "80%",
        maxWidth: 300,
        alignItems: "center",
    },
    jumpTitle: {
        fontSize: 18,
        fontWeight: "bold",
        marginBottom: 16,
        color: "#333",
    },
    jumpInput: {
        borderWidth: 1,
        borderColor: "#ddd",
        borderRadius: 8,
        padding: 10,
        width: "100%",
        textAlign: "center",
        fontSize: 18,
        marginBottom: 16,
    },
    jumpButtons: {
        flexDirection: "row",
        gap: 12,
        width: "100%",
    },
    jumpCancel: {
        flex: 1,
        padding: 12,
        borderRadius: 8,
        backgroundColor: "#f0f0f0",
        alignItems: "center",
    },
    jumpCancelText: {
        color: "#666",
        fontWeight: "600",
    },
    jumpGo: {
        flex: 1,
        padding: 12,
        borderRadius: 8,
        backgroundColor: "#007AFF",
        alignItems: "center",
    },
    jumpGoText: {
        color: "white",
        fontWeight: "600",
    },
    outlinePanel: {
        backgroundColor: "white",
        borderTopLeftRadius: 20,
        borderTopRightRadius: 20,
        width: "100%",
        maxHeight: "70%",
        marginTop: "auto",
        paddingBottom: 20,
    },
    outlineHeader: {
        flexDirection: "row",
        justifyContent: "space-between",
        alignItems: "center",
        padding: 16,
        borderBottomWidth: 1,
        borderBottomColor: "#eee",
    },
    outlineTitle: {
        fontSize: 18,
        fontWeight: "bold",
        color: "#333",
    },
    outlineList: {
        paddingHorizontal: 16,
    },
    outlineItem: {
        flexDirection: "row",
        justifyContent: "space-between",
        alignItems: "center",
        paddingVertical: 12,
        borderBottomWidth: 1,
        borderBottomColor: "#f5f5f5",
    },
    outlineItemTitle: {
        fontSize: 14,
        color: "#333",
        flex: 1,
        marginRight: 10,
    },
    outlineItemPage: {
        fontSize: 12,
        color: "#999",
    },
    toast: {
        position: "absolute",
        left: 20,
        right: 20,
        backgroundColor: "rgba(0,0,0,0.85)",
        paddingVertical: 10,
        paddingHorizontal: 16,
        borderRadius: 20,
        alignItems: "center",
        zIndex: 9999,
    },
    toastText: {
        color: "#ffffff",
        fontSize: 13,
        fontWeight: "600",
    },
});
