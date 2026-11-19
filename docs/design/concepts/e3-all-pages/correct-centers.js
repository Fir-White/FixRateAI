// Deferred correction after font/token application and a fresh measured audit.
// Supply SECTION and CORRECTIONS = qa-final.frames[].badCenters for that page.
// A separate read is intentional: a just-resized component may still have cached glyph metrics.
const p=penpot.currentFile.pages.find(p=>p.getPluginData('suite-section')===SECTION);await penpot.openPage(p);
const token=penpot.history.undoBlockBegin();try{for(const f of CORRECTIONS){const t=p.getShapeById(f.id);if(!t||t.type!=='text')throw Error('Missing text '+f.id);t.x-=f.x;t.y-=f.y;}return {corrected:CORRECTIONS.length};}finally{penpot.history.undoBlockFinish(token);}
