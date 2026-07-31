const TARGET = "http://127.0.0.1:8787/";

function openX2RED(url) {
  const target = `${TARGET}?url=${encodeURIComponent(url)}`;
  chrome.tabs.create({ url: target });
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "send-to-x2red",
    title: "Send to X2RED",
    contexts: ["page", "link"],
    documentUrlPatterns: ["https://x.com/*", "https://twitter.com/*"],
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  openX2RED(info.linkUrl || info.pageUrl || tab?.url || "");
});

chrome.action.onClicked.addListener((tab) => {
  if (tab.url) openX2RED(tab.url);
});
