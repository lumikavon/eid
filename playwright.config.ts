import {defineConfig} from '@playwright/test';
export default defineConfig({
  testDir:'tests/ux', timeout:60000, workers:1,
  use:{baseURL:'http://localhost:18080',channel:'chrome',viewport:{width:1920,height:1080},trace:'off',launchOptions:{args:['--disable-gpu','--force-color-profile=srgb']}},
  reporter:'list',
});
