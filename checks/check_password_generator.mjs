import assert from 'node:assert/strict';
import {generatePassword} from '../web/password-generator.js';

const categories = [/[A-HJ-NP-Z]/,/[a-hjkmnp-z]/,/[2-9]/,/[!@#$%^&*]/];
const site = 'synthetic-site', seed = 'synthetic-seed';
for (let length = 12; length <= 64; length++) {
  const value = await generatePassword(site,seed,length);
  assert.equal(value.length,length,'Every supported length must be exact');
  assert.ok(categories.every(category => category.test(value)),'Every category must be present');
  assert.ok(value === await generatePassword(site,seed,length),'Matching inputs must be reproducible');
}
for (let i = 0; i < 256; i++) {
  const value = await generatePassword(site,seed + '-' + i,12);
  assert.ok(categories.every(category => category.test(value)),'Required categories survive the shuffle');
}
const value = await generatePassword(site,seed,16);
assert.ok(value !== await generatePassword('another-site',seed,16),'The site separates generated values');
assert.ok(value !== await generatePassword(site,'another-seed',16),'The seed separates generated values');
assert.ok(value === await generatePassword(' SYNTHETIC-SITE ',' synthetic-seed ',16),'Input normalization stays stable');
for (const length of [0,11,65,12.5,NaN,'16']) {
  await assert.rejects(generatePassword(site,seed,length),/12 到 64/);
}
for (const [badSite,badSeed] of [['',seed],[site,' '],[null,seed],[site,null]]) {
  await assert.rejects(generatePassword(badSite,badSeed,16),/平台名/);
}
console.log('password generator: exact lengths 12–64, four categories, deterministic inputs and validation passed');
