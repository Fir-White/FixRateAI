'use strict';

const parentOrigin = /^http:\/\/127\.0\.0\.1(?::\d+)?$/.test(location.hash.slice(1)) ? location.hash.slice(1) : '';
let editor;

function compactStatusBar() {
  const frame = document.querySelector('main iframe');
  if (!frame?.contentDocument?.head) return;
  frame.contentDocument.getElementById('fixrate-narrow-layout')?.remove();
  const style = frame.contentDocument.createElement('style');
  style.id = 'fixrate-narrow-layout';
  // At narrow widths the calculation status overlaps the sheet tabs in Docs 10.
  style.textContent = '@media(max-width:550px){#status-math-box{display:none!important}}';
  frame.contentDocument.head.appendChild(style);
  frame.contentWindow.dispatchEvent(new Event('resize'));
}

function notify(event, fields = {}) {
  if (parentOrigin) parent.postMessage({bridge: 'fixrate-office', event, ...fields}, parentOrigin);
}

window.addEventListener('message', event => {
  if (!parentOrigin || event.source !== parent || event.origin !== parentOrigin
    || event.data?.bridge !== 'fixrate-office' || event.data?.event !== 'init' || editor) return;
  const config = event.data.config;
  if (!config || typeof config !== 'object' || config.documentType !== 'cell') {
    notify('error');
    return;
  }
  try {
    editor = new window.DocsAPI.DocEditor('workbook-office', {
      ...config,
      events: {
        onDocumentReady: () => {compactStatusBar();notify('ready');},
        onDocumentStateChange: ({data}) => notify('sync', {syncing: data === true}),
        onError: () => notify('error'),
      },
    });
  } catch {
    notify('error');
  }
});
