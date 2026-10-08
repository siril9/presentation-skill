import { AppBridge, PostMessageTransport } from '@modelcontextprotocol/ext-apps/app-bridge';

const iframe = document.createElement('iframe');
iframe.title = 'Slide Review';
iframe.style.cssText = 'display:block;border:0;width:100vw;height:100vh';
document.body.style.margin = '0';
document.body.append(iframe);
window.previewCalls = [];
window.previewContexts = [];
window.previewMessages = [];
const bridge = new AppBridge(null, { name: 'Preview browser harness', version: '1.0.0' }, {
  serverTools: {}, updateModelContext: { text: {}, structuredContent: {} }, message: { text: {} },
}, { hostContext: { theme: 'light', displayMode: 'inline' } });
bridge.oncalltool = async (args) => {
  window.previewCalls.push(args);
  return window.callPreviewTool(args);
};
bridge.onupdatemodelcontext = async (args) => { window.previewContexts.push(args); return {}; };
bridge.onmessage = async (args) => { window.previewMessages.push(args); return {}; };
bridge.oninitialized = async () => {
  await bridge.sendToolInput({ arguments: { deck_id: window.previewDeckId } });
  await bridge.sendToolResult(await window.initialPreviewResult());
};
await bridge.connect(new PostMessageTransport(iframe.contentWindow, iframe.contentWindow));
iframe.src = '/preview';
