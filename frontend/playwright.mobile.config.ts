import playwright from '@playwright/test';
import base from './playwright.config';
const {defineConfig}=playwright;

// Same real API workflow as desktop, with native browser mobile layout/touch.
// This does not emulate a physical operating-system software keyboard.
export default defineConfig({
  ...base,
  testMatch:'maintenance.spec.ts',
  use:{...base.use,viewport:{width:390,height:844},isMobile:true,hasTouch:true},
});
