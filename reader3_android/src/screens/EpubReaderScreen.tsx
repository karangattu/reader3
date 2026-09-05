import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
    View, StyleSheet, TouchableOpacity, Text,
    Alert, ActivityIndicator, FlatList, Modal,
} from 'react-native';
import { WebView, WebViewMessageEvent } from 'react-native-webview';
import { File } from 'expo-file-system';
import * as Clipboard from 'expo-clipboard';
import { useRoute, useNavigation } from '@react-navigation/native';
import { BookEntry } from './LibraryScreen';
import JSZip from 'jszip';
import AsyncStorage from '@react-native-async-storage/async-storage';
import FontAwesome from '@expo/vector-icons/FontAwesome';
import {
    TOCEntry,
    htmlToPlainText,
    parseAttributes,
    parseNCX,
    parseNavToc,
    formatChaptersForClipboard,
} from '../utils/textHelpers.ts';
import { extractEpubCover } from '../utils/coverHelpers.ts';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

type ManifestItem = { href: string; mediaType: string };

export default function EpubReaderScreen() {
    const route = useRoute<any>();
    const navigation = useNavigation<any>();
    const book = route.params?.book as BookEntry;
    const webviewRef = useRef<WebView>(null);
    const insets = useSafeAreaInsets();

    const [chapters, setChapters] = useState<{ html: string; plainText: string; href: string }[]>([]);
    const [toc, setToc] = useState<TOCEntry[]>([]);
    const [currentChapter, setCurrentChapter] = useState(0);
    const [loading, setLoading] = useState(true);
    const [tocVisible, setTocVisible] = useState(false);
    const [multiSelectMode, setMultiSelectMode] = useState(false);
    const [selectedChapters, setSelectedChapters] = useState<Set<number>>(new Set());
    const [copiedChapters, setCopiedChapters] = useState<Set<number>>(new Set());
    const [readProgress, setReadProgress] = useState<Record<number, number>>({});
    const [toastMessage, setToastMessage] = useState<string | null>(null);

    const showToast = useCallback((msg: string) => {
        setToastMessage(msg);
        setTimeout(() => setToastMessage(null), 2000);
    }, []);

    const loadProgress = useCallback(async () => {
        if (!book?.id) return;
        try {
            const data = await AsyncStorage.getItem(`@reader3:progress:${book.id}`);
            if (data) {
                const parsed = JSON.parse(data);
                setReadProgress(parsed.chapterProgress || {});
                if (parsed.lastChapter !== undefined) {
                    setCurrentChapter(parsed.lastChapter);
                }
                if (parsed.copiedChapters) {
                    setCopiedChapters(new Set(parsed.copiedChapters));
                }
            }
        } catch { }
    }, [book?.id]);

    const saveProgress = useCallback(async (chapterIdx: number, progress?: number, newCopied?: Set<number>) => {
        if (!book?.id) return;
        try {
            const newProgress = { ...readProgress };
            if (progress !== undefined) newProgress[chapterIdx] = progress;
            setReadProgress(newProgress);
            const copiedList = Array.from(newCopied || copiedChapters);
            await AsyncStorage.setItem(`@reader3:progress:${book.id}`, JSON.stringify({
                lastChapter: chapterIdx,
                chapterProgress: newProgress,
                copiedChapters: copiedList,
            }));
        } catch { }
    }, [book?.id, readProgress, copiedChapters]);

    const loadEpub = useCallback(async () => {
        if (!book?.uri) return;
        try {
            setLoading(true);
            const file = new File(book.uri);
            const data = await file.arrayBuffer();
            const zip = await JSZip.loadAsync(data);

            const containerXml = await zip.file('META-INF/container.xml')?.async('text');
            if (!containerXml) throw new Error('Invalid EPUB: missing container.xml');

            const rootfileMatch = containerXml.match(/rootfile[^>]+full-path="([^"]+)"/);
            if (!rootfileMatch) throw new Error('Invalid EPUB: no rootfile found');

            const opfPath = rootfileMatch[1];
            const opfDir = opfPath.includes('/') ? opfPath.substring(0, opfPath.lastIndexOf('/') + 1) : '';

            const opfContent = await zip.file(opfPath)?.async('text');
            if (!opfContent) throw new Error('Invalid EPUB: missing OPF file');

            const manifest: Record<string, ManifestItem> = {};
            const itemRegex = /<item\s+([^>]+?)\/?>/g;
            let match;
            while ((match = itemRegex.exec(opfContent)) !== null) {
                const attrs = parseAttributes(match[1]);
                if (attrs.id && attrs.href) {
                    manifest[attrs.id] = {
                        href: attrs.href,
                        mediaType: attrs['media-type'] || '',
                    };
                }
            }

            const spineItemRefs: string[] = [];
            const spineRegex = /<itemref\s+([^>]+?)\/?>/g;
            while ((match = spineRegex.exec(opfContent)) !== null) {
                const attrs = parseAttributes(match[1]);
                if (attrs.idref) spineItemRefs.push(attrs.idref);
            }

            if (spineItemRefs.length === 0) throw new Error('Invalid EPUB: empty spine');

            let tocEntries: TOCEntry[] = [];
            const ncxItem = Object.values(manifest).find(i => i.mediaType === 'application/x-dtbncx+xml');
            if (ncxItem) {
                const ncxPath = opfDir + decodeURIComponent(ncxItem.href);
                const ncxContent = await zip.file(ncxPath)?.async('text');
                if (ncxContent) tocEntries = parseNCX(ncxContent);
            }
            if (tocEntries.length === 0) {
                const navItem = Object.entries(manifest).find(([, i]) =>
                    i.mediaType === 'application/xhtml+xml' && opfContent.includes(`properties="nav"`)
                );
                if (navItem) {
                    const navPath = opfDir + decodeURIComponent(navItem[1].href);
                    const navContent = await zip.file(navPath)?.async('text');
                    if (navContent) tocEntries = parseNavToc(navContent);
                }
            }
            setToc(tocEntries);

            const chapterContents: { html: string; plainText: string; href: string }[] = [];
            for (const idref of spineItemRefs) {
                const item = manifest[idref];
                if (!item) continue;

                const chapterPath = opfDir + decodeURIComponent(item.href);
                const chapterDir = chapterPath.includes('/')
                    ? chapterPath.substring(0, chapterPath.lastIndexOf('/') + 1)
                    : opfDir;

                let content = await zip.file(chapterPath)?.async('text');
                if (!content) continue;

                const imgRegex = /(?:src|xlink:href)="([^"]+)"/g;
                let imgMatch;
                const replacements: [string, string][] = [];
                while ((imgMatch = imgRegex.exec(content)) !== null) {
                    const imgSrc = imgMatch[1];
                    if (imgSrc.startsWith('data:') || imgSrc.startsWith('http')) continue;
                    const imgPath = imgSrc.startsWith('/') ? imgSrc.substring(1) : chapterDir + imgSrc;
                    try {
                        const imgData = await zip.file(imgPath)?.async('base64');
                        if (imgData) {
                            const ext = imgSrc.split('.').pop()?.toLowerCase() || '';
                            let mime = 'image/png';
                            if (ext === 'jpg' || ext === 'jpeg') mime = 'image/jpeg';
                            else if (ext === 'gif') mime = 'image/gif';
                            else if (ext === 'svg') mime = 'image/svg+xml';
                            replacements.push([imgSrc, `data:${mime};base64,${imgData}`]);
                        }
                    } catch { }
                }
                for (const [from, to] of replacements) {
                    content = content.split(from).join(to);
                }

                const cssRegex = /href="([^"]+\.css)"/g;
                let cssMatch;
                const cssReplacements: [string, string][] = [];
                while ((cssMatch = cssRegex.exec(content)) !== null) {
                    const cssHref = cssMatch[1];
                    const cssPath = cssHref.startsWith('/') ? cssHref.substring(1) : chapterDir + cssHref;
                    try {
                        const cssData = await zip.file(cssPath)?.async('text');
                        if (cssData) {
                            cssReplacements.push([
                                cssMatch[0],
                                `data-inlined="true"><style>${cssData}</style><span style="display:none"`,
                            ]);
                        }
                    } catch { }
                }
                for (const [from, to] of cssReplacements) {
                    content = content.replace(from, to);
                }

                const plainText = htmlToPlainText(content);
                chapterContents.push({ html: content, plainText, href: item.href });
            }

            if (chapterContents.length === 0) throw new Error('Could not extract any chapters.');

            setChapters(chapterContents);

            if (!book?.coverUri && book?.id) {
                extractEpubCover(book.uri, book.id).then(async (cUri) => {
                    if (cUri) {
                        const stored = await AsyncStorage.getItem('@reader3:books');
                        if (stored) {
                            const books: BookEntry[] = JSON.parse(stored);
                            const idx = books.findIndex(b => b.id === book.id);
                            if (idx >= 0) {
                                books[idx].coverUri = cUri;
                                await AsyncStorage.setItem('@reader3:books', JSON.stringify(books));
                            }
                        }
                    }
                }).catch(() => {});
            }
        } catch (err: any) {
            Alert.alert('Error', 'Failed to load EPUB: ' + (err.message || String(err)));
        } finally {
            setLoading(false);
        }
    }, [book?.uri, book?.coverUri, book?.id]);

    useEffect(() => {
        if (book?.uri) {
            loadEpub();
            loadProgress();
        }
    }, [book?.uri, loadEpub, loadProgress]);

    const goToChapter = (index: number) => {
        if (index >= 0 && index < chapters.length) {
            setCurrentChapter(index);
            saveProgress(index);
            setTocVisible(false);
        }
    };

    const findChapterByHref = (href: string): number => {
        const cleanHref = href.split('#')[0];
        const basename = cleanHref.split('/').pop();
        let idx = chapters.findIndex(c => c.href === cleanHref);
        if (idx === -1 && basename) {
            idx = chapters.findIndex(c => c.href.endsWith(basename));
        }
        return idx >= 0 ? idx : 0;
    };

    const getChapterTitle = (index: number): string => {
        if (toc.length > 0 && chapters.length > 0) {
            const chapter = chapters[index];
            if (!chapter) return `Chapter ${index + 1}`;
            const basename = chapter.href.split('/').pop()?.split('#')[0];
            const entry = toc.find(t => {
                const tocBase = t.href.split('/').pop()?.split('#')[0];
                return tocBase === basename;
            });
            if (entry) return entry.title;
        }
        return `Chapter ${index + 1}`;
    };

    const copyChapterText = async () => {
        if (chapters.length === 0) return;
        const text = chapters[currentChapter].plainText;
        const formatted = `=== ${getChapterTitle(currentChapter)} ===\n\n${text}`;
        await Clipboard.setStringAsync(formatted);
        showToast(`Chapter text copied (${text.length} chars)`);
        const updated = new Set(copiedChapters);
        updated.add(currentChapter);
        setCopiedChapters(updated);
        saveProgress(currentChapter, 100, updated);
    };

    const copySingleChapter = async (index: number) => {
        if (!chapters[index]) return;
        const text = chapters[index].plainText;
        const formatted = `=== ${getChapterTitle(index)} ===\n\n${text}`;
        await Clipboard.setStringAsync(formatted);
        showToast(`Copied ${getChapterTitle(index)}`);
        const updated = new Set(copiedChapters);
        updated.add(index);
        setCopiedChapters(updated);
        saveProgress(currentChapter, readProgress[index] || 100, updated);
    };

    const copySelectedChaptersText = async () => {
        if (selectedChapters.size === 0) return;
        const sorted = Array.from(selectedChapters).sort((a, b) => a - b);
        const dataToFormat = sorted.map(i => ({
            title: getChapterTitle(i),
            text: chapters[i].plainText,
        }));
        const combined = formatChaptersForClipboard(dataToFormat);
        await Clipboard.setStringAsync(combined);
        showToast(`${sorted.length} chapters copied (${combined.length} chars)`);
        const updated = new Set(copiedChapters);
        sorted.forEach(idx => updated.add(idx));
        setCopiedChapters(updated);
        saveProgress(currentChapter, undefined, updated);
        setSelectedChapters(new Set());
        setMultiSelectMode(false);
    };

    const toggleChapterSelect = (index: number) => {
        const newSet = new Set(selectedChapters);
        if (newSet.has(index)) newSet.delete(index);
        else newSet.add(index);
        setSelectedChapters(newSet);
    };

    const selectAllChapters = () => {
        const all = new Set<number>();
        for (let i = 0; i < chapters.length; i++) all.add(i);
        setSelectedChapters(all);
    };

    const clearChapterSelection = () => {
        setSelectedChapters(new Set());
    };

    const onWebViewMessage = (event: WebViewMessageEvent) => {
        try {
            const data = JSON.parse(event.nativeEvent.data);
            if (data.type === 'copy') {
                Clipboard.setStringAsync(data.text);
                showToast('Text copied!');
            } else if (data.type === 'scrollProgress') {
                saveProgress(currentChapter, Math.round(data.progress));
            }
        } catch { }
    };

    const wrapChapterHTML = (html: string) => {
        const bodyMatch = html.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
        const bodyContent = bodyMatch ? bodyMatch[1] : html;
        const styleMatches = html.match(/<style[^>]*>([\s\S]*?)<\/style>/gi) || [];
        const inlinedStyles = styleMatches.join('\n');

        return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=3.0, user-scalable=yes">
${inlinedStyles}
<style>
    body {
        font-family: Georgia, 'Times New Roman', serif;
        line-height: 1.8;
        padding: 16px;
        padding-bottom: 60px;
        margin: 0;
        color: #222;
        background: #fff;
        font-size: 18px;
        word-wrap: break-word;
        overflow-wrap: break-word;
        -webkit-user-select: text;
        user-select: text;
    }
    img { max-width: 100%; height: auto; }
    h1, h2, h3 { color: #111; position: relative; }
    a { color: #007AFF; }
    pre, code { white-space: pre-wrap; word-wrap: break-word; }

    .heading-copy-btn {
        margin-left: 8px;
        font-size: 13px;
        padding: 2px 8px;
        border-radius: 6px;
        border: 1px solid #d0d7ff;
        background: #eef2ff;
        color: #2c3e50;
        cursor: pointer;
        vertical-align: middle;
        font-family: -apple-system, sans-serif;
    }

    #copy-fab {
        position: fixed;
        bottom: 16px;
        right: 16px;
        background: #007AFF;
        color: white;
        border: none;
        border-radius: 28px;
        padding: 12px 20px;
        font-size: 15px;
        font-weight: 600;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        z-index: 9999;
        display: none;
        cursor: pointer;
    }
    #copy-fab.visible { display: block; }
</style>
</head>
<body>
${bodyContent}
<button id="copy-fab" onclick="copySelection()">Copy Selection</button>
<script>
    document.querySelectorAll('h1, h2, h3').forEach(function(h) {
        if (h.querySelector('.heading-copy-btn')) return;
        var btn = document.createElement('button');
        btn.className = 'heading-copy-btn';
        btn.innerText = 'Copy';
        btn.onclick = function(e) {
            e.stopPropagation();
            var clone = h.cloneNode(true);
            var b = clone.querySelector('.heading-copy-btn');
            if (b) b.remove();
            var text = (clone.textContent || '').trim();
            if (text) {
                window.ReactNativeWebView.postMessage(JSON.stringify({type: 'copy', text: text}));
                btn.innerText = 'Copied!';
                setTimeout(function() { btn.innerText = 'Copy'; }, 1500);
            }
        };
        h.appendChild(btn);
    });

    document.addEventListener('selectionchange', function() {
        var sel = window.getSelection();
        var text = sel ? sel.toString().trim() : '';
        var fab = document.getElementById('copy-fab');
        if (text.length > 0) {
            fab.classList.add('visible');
        } else {
            fab.classList.remove('visible');
        }
    });

    function copySelection() {
        var sel = window.getSelection();
        var text = sel ? sel.toString().trim() : '';
        if (text) {
            window.ReactNativeWebView.postMessage(JSON.stringify({type: 'copy', text: text}));
            sel.removeAllRanges();
            document.getElementById('copy-fab').classList.remove('visible');
        }
    }

    var lastProgress = 0;
    window.addEventListener('scroll', function() {
        var scrollTop = window.scrollY || document.documentElement.scrollTop;
        var scrollHeight = document.documentElement.scrollHeight - window.innerHeight;
        var progress = scrollHeight > 0 ? (scrollTop / scrollHeight) * 100 : 100;
        if (Math.abs(progress - lastProgress) > 2) {
            lastProgress = progress;
            window.ReactNativeWebView.postMessage(JSON.stringify({type: 'scrollProgress', progress: progress}));
        }
    });
</script>
</body>
</html>`;
    };

    if (!book) {
        return (
            <View style={styles.center}>
                <Text style={styles.errorText}>No book provided</Text>
            </View>
        );
    }

    const renderTocItem = ({ item }: { item: TOCEntry; index: number }) => {
        const chapterIdx = findChapterByHref(item.href);
        const progress = readProgress[chapterIdx] || 0;
        const isSelected = selectedChapters.has(chapterIdx);
        const isCopied = copiedChapters.has(chapterIdx);

        return (
            <View
                style={[
                    styles.tocItem,
                    chapterIdx === currentChapter && styles.tocItemActive,
                    isSelected && styles.tocItemSelected,
                ]}
            >
                <TouchableOpacity
                    style={styles.tocItemMain}
                    onPress={() => {
                        if (multiSelectMode) {
                            toggleChapterSelect(chapterIdx);
                        } else {
                            goToChapter(chapterIdx);
                        }
                    }}
                    onLongPress={() => {
                        if (!multiSelectMode) {
                            setMultiSelectMode(true);
                            toggleChapterSelect(chapterIdx);
                        }
                    }}
                >
                    {multiSelectMode && (
                        <View style={[styles.checkbox, isSelected && styles.checkboxChecked]}>
                            {isSelected && <FontAwesome name="check" size={12} color="#fff" />}
                        </View>
                    )}
                    <View style={styles.tocTextContainer}>
                        <View style={styles.tocTitleRow}>
                            <Text style={[
                                styles.tocTitle,
                                chapterIdx === currentChapter && styles.tocTitleActive,
                            ]} numberOfLines={2}>
                                {item.title}
                            </Text>
                            {isCopied && (
                                <View style={styles.copiedBadge}>
                                    <Text style={styles.copiedBadgeText}>Copied</Text>
                                </View>
                            )}
                        </View>
                        {progress > 0 && (
                            <View style={styles.tocProgressBar}>
                                <View style={[styles.tocProgressFill, { width: `${Math.min(progress, 100)}%` }]} />
                            </View>
                        )}
                    </View>
                </TouchableOpacity>
                {!multiSelectMode && (
                    <TouchableOpacity
                        style={styles.singleCopyBtn}
                        onPress={() => copySingleChapter(chapterIdx)}
                    >
                        <Text style={styles.singleCopyText}>Copy</Text>
                    </TouchableOpacity>
                )}
            </View>
        );
    };

    const displayToc = toc.length > 0 ? toc : chapters.map((c, i) => ({
        title: getChapterTitle(i),
        href: c.href,
        children: [],
    }));

    return (
        <View style={[styles.safeArea, { paddingTop: insets.top }]}>
            <View style={styles.header}>
                <TouchableOpacity style={styles.headerBtn} onPress={() => navigation.goBack()}>
                    <FontAwesome name="arrow-left" size={18} color="#007AFF" />
                </TouchableOpacity>
                <TouchableOpacity style={styles.titleContainer} onPress={() => setTocVisible(true)}>
                    <Text style={styles.title} numberOfLines={1}>{getChapterTitle(currentChapter)}</Text>
                    <Text style={styles.chapterCounter}>{currentChapter + 1}/{chapters.length || '...'}</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.headerBtn} onPress={copyChapterText}>
                    <FontAwesome name="clipboard" size={18} color="#007AFF" />
                </TouchableOpacity>
                <TouchableOpacity style={styles.headerBtn} onPress={() => setTocVisible(true)}>
                    <FontAwesome name="bars" size={18} color="#007AFF" />
                </TouchableOpacity>
            </View>

            <View style={styles.container}>
                {loading ? (
                    <View style={styles.center}>
                        <ActivityIndicator size="large" color="#007AFF" />
                        <Text style={styles.loadingText}>Loading EPUB...</Text>
                    </View>
                ) : chapters.length > 0 ? (
                    <WebView
                        key={currentChapter}
                        ref={webviewRef}
                        originWhitelist={['*']}
                        source={{ html: wrapChapterHTML(chapters[currentChapter].html) }}
                        style={styles.webview}
                        showsVerticalScrollIndicator={true}
                        javaScriptEnabled={true}
                        onMessage={onWebViewMessage}
                    />
                ) : (
                    <View style={styles.center}>
                        <Text style={styles.errorText}>Could not load chapters.</Text>
                    </View>
                )}

                {!loading && chapters.length > 0 && (
                    <View style={[styles.controls, { paddingBottom: Math.max(insets.bottom + 10, 16) }]}>
                        <TouchableOpacity
                            style={[styles.controlButton, currentChapter === 0 && styles.controlButtonDisabled]}
                            onPress={() => goToChapter(currentChapter - 1)}
                            disabled={currentChapter === 0}
                        >
                            <View style={styles.controlContent}>
                                <FontAwesome name="chevron-left" size={12} color="#ffffff" />
                                <Text style={styles.controlText}> Prev</Text>
                            </View>
                        </TouchableOpacity>
                        <TouchableOpacity style={styles.copyButton} onPress={copyChapterText}>
                            <View style={styles.controlContent}>
                                <FontAwesome name="clipboard" size={13} color="#ffffff" />
                                <Text style={styles.controlText}> Copy Chapter</Text>
                            </View>
                        </TouchableOpacity>
                        <TouchableOpacity
                            style={[styles.controlButton, currentChapter === chapters.length - 1 && styles.controlButtonDisabled]}
                            onPress={() => goToChapter(currentChapter + 1)}
                            disabled={currentChapter === chapters.length - 1}
                        >
                            <View style={styles.controlContent}>
                                <Text style={styles.controlText}>Next </Text>
                                <FontAwesome name="chevron-right" size={12} color="#ffffff" />
                            </View>
                        </TouchableOpacity>
                    </View>
                )}
            </View>

            <Modal visible={tocVisible} animationType="slide" transparent>
                <View style={styles.modalOverlay}>
                    <View style={[styles.tocPanel, { paddingBottom: Math.max(insets.bottom + 16, 24) }]}>
                        <View style={styles.tocHeader}>
                            <Text style={styles.tocHeaderTitle}>Table of Contents</Text>
                            <TouchableOpacity onPress={() => {
                                setTocVisible(false);
                                setMultiSelectMode(false);
                                setSelectedChapters(new Set());
                            }}>
                                <FontAwesome name="times" size={20} color="#666" />
                            </TouchableOpacity>
                        </View>

                        {multiSelectMode && (
                            <View style={styles.multiSelectBar}>
                                <Text style={styles.multiSelectText}>
                                    {selectedChapters.size} selected
                                </Text>
                                <TouchableOpacity style={styles.pillBtn} onPress={selectAllChapters}>
                                    <Text style={styles.pillBtnText}>Select All</Text>
                                </TouchableOpacity>
                                <TouchableOpacity style={styles.pillBtn} onPress={clearChapterSelection}>
                                    <Text style={styles.pillBtnText}>Clear</Text>
                                </TouchableOpacity>
                                <TouchableOpacity
                                    style={[styles.multiCopyBtn, selectedChapters.size === 0 && styles.disabledBtn]}
                                    onPress={copySelectedChaptersText}
                                    disabled={selectedChapters.size === 0}
                                >
                                    <Text style={styles.multiCopyBtnText}>Copy</Text>
                                </TouchableOpacity>
                                <TouchableOpacity
                                    onPress={() => {
                                        setMultiSelectMode(false);
                                        setSelectedChapters(new Set());
                                    }}
                                >
                                    <Text style={styles.cancelText}>Cancel</Text>
                                </TouchableOpacity>
                            </View>
                        )}

                        <FlatList
                            data={displayToc}
                            keyExtractor={(_, i) => String(i)}
                            renderItem={renderTocItem}
                            contentContainerStyle={styles.tocList}
                        />

                        {!multiSelectMode && (
                            <TouchableOpacity
                                style={styles.multiSelectStartBtn}
                                onPress={() => setMultiSelectMode(true)}
                            >
                                <Text style={styles.multiSelectStartText}>Select Multiple Chapters to Copy</Text>
                            </TouchableOpacity>
                        )}
                    </View>
                </View>
            </Modal>

            {toastMessage && (
                <View style={[styles.toast, { bottom: Math.max(insets.bottom + 80, 100) }]}>
                    <Text style={styles.toastText}>{toastMessage}</Text>
                </View>
            )}
        </View>
    );
}

const styles = StyleSheet.create({
    safeArea: {
        flex: 1,
        backgroundColor: '#ffffff',
    },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        padding: 10,
        borderBottomWidth: 1,
        borderBottomColor: '#e0e0e0',
        backgroundColor: '#ffffff',
    },
    headerBtn: {
        padding: 8,
        minWidth: 40,
        alignItems: 'center',
    },
    headerBtnText: {
        fontSize: 20,
    },
    titleContainer: {
        flex: 1,
        alignItems: 'center',
        paddingHorizontal: 4,
    },
    title: {
        fontSize: 15,
        fontWeight: '600',
        color: '#333',
    },
    chapterCounter: {
        fontSize: 12,
        color: '#8e8e93',
        marginTop: 2,
    },
    container: { flex: 1, backgroundColor: '#ffffff' },
    webview: { flex: 1, backgroundColor: '#ffffff' },
    controls: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        padding: 8,
        backgroundColor: '#ffffff',
        borderTopWidth: 1,
        borderTopColor: '#e0e0e0',
    },
    controlButton: {
        paddingVertical: 10,
        paddingHorizontal: 16,
        backgroundColor: '#007AFF',
        borderRadius: 8,
    },
    controlButtonDisabled: { backgroundColor: '#ccc' },
    copyButton: {
        paddingVertical: 10,
        paddingHorizontal: 16,
        backgroundColor: '#34C759',
        borderRadius: 8,
    },
    controlText: { color: '#fff', fontWeight: '600', fontSize: 14 },
    controlContent: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center' },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
    loadingText: { fontSize: 16, color: '#8e8e93', marginTop: 12 },
    errorText: { fontSize: 18, color: '#FF3B30' },

    modalOverlay: {
        flex: 1,
        backgroundColor: 'rgba(0,0,0,0.5)',
        justifyContent: 'flex-end',
    },
    tocPanel: {
        backgroundColor: '#fff',
        borderTopLeftRadius: 20,
        borderTopRightRadius: 20,
        maxHeight: '85%',
        paddingBottom: 30,
    },
    tocHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: 16,
        borderBottomWidth: 1,
        borderBottomColor: '#eee',
    },
    tocHeaderTitle: { fontSize: 18, fontWeight: '700', color: '#333' },
    tocCloseBtn: { fontSize: 22, color: '#8e8e93', padding: 4 },
    tocList: { paddingHorizontal: 16, paddingTop: 8 },
    tocItem: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingVertical: 10,
        paddingHorizontal: 12,
        borderBottomWidth: 1,
        borderBottomColor: '#f0f0f0',
        borderRadius: 8,
        marginBottom: 2,
    },
    tocItemMain: {
        flexDirection: 'row',
        alignItems: 'center',
        flex: 1,
    },
    tocItemActive: { backgroundColor: '#E8F4FD' },
    tocItemSelected: { backgroundColor: '#D4EDDA' },
    tocTextContainer: { flex: 1 },
    tocTitleRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
    },
    tocTitle: { fontSize: 15, color: '#333', flex: 1 },
    tocTitleActive: { fontWeight: '700', color: '#007AFF' },
    copiedBadge: {
        backgroundColor: '#27ae60',
        paddingHorizontal: 6,
        paddingVertical: 2,
        borderRadius: 4,
        marginLeft: 6,
    },
    copiedBadgeText: {
        color: '#fff',
        fontSize: 10,
        fontWeight: 'bold',
    },
    singleCopyBtn: {
        backgroundColor: '#f0f0f2',
        paddingHorizontal: 10,
        paddingVertical: 5,
        borderRadius: 6,
        marginLeft: 8,
    },
    singleCopyText: {
        color: '#007AFF',
        fontSize: 12,
        fontWeight: '600',
    },
    tocProgressBar: {
        height: 3,
        backgroundColor: '#e0e0e0',
        borderRadius: 2,
        marginTop: 6,
    },
    tocProgressFill: {
        height: 3,
        backgroundColor: '#34C759',
        borderRadius: 2,
    },
    checkbox: {
        width: 22,
        height: 22,
        borderRadius: 4,
        borderWidth: 2,
        borderColor: '#007AFF',
        marginRight: 10,
        justifyContent: 'center',
        alignItems: 'center',
    },
    checkboxChecked: { backgroundColor: '#007AFF' },
    checkmark: { color: '#fff', fontWeight: '700', fontSize: 12 },
    multiSelectBar: {
        flexDirection: 'row',
        alignItems: 'center',
        padding: 10,
        backgroundColor: '#f0f9f0',
        borderBottomWidth: 1,
        borderBottomColor: '#ddd',
        gap: 6,
    },
    multiSelectText: { flex: 1, fontSize: 13, color: '#333', fontWeight: '600' },
    pillBtn: {
        backgroundColor: '#fff',
        borderColor: '#ccc',
        borderWidth: 1,
        paddingHorizontal: 8,
        paddingVertical: 4,
        borderRadius: 4,
    },
    pillBtnText: { color: '#333', fontSize: 12, fontWeight: '500' },
    multiCopyBtn: {
        backgroundColor: '#34C759',
        paddingHorizontal: 12,
        paddingVertical: 6,
        borderRadius: 6,
    },
    disabledBtn: {
        backgroundColor: '#ccc',
    },
    multiCopyBtnText: { color: '#fff', fontWeight: '600', fontSize: 12 },
    cancelText: { color: '#FF3B30', fontWeight: '500', fontSize: 13, marginLeft: 4 },
    multiSelectStartBtn: {
        margin: 16,
        padding: 14,
        backgroundColor: '#f5f5f7',
        borderRadius: 10,
        alignItems: 'center',
    },
    multiSelectStartText: { color: '#007AFF', fontWeight: '600', fontSize: 15 },
    toast: {
        position: 'absolute',
        bottom: 100,
        alignSelf: 'center',
        backgroundColor: 'rgba(0,0,0,0.8)',
        paddingHorizontal: 20,
        paddingVertical: 10,
        borderRadius: 20,
    },
    toastText: { color: '#fff', fontSize: 14, fontWeight: '500' },
});
