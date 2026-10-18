import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {generatePassword} from '../web/password-generator.js';

const categories = [/[A-HJ-NP-Z]/,/[a-hjkmnp-z]/,/[2-9]/,/[!@#$%^&*]/];
const site = 'synthetic-site', seed = 'synthetic-seed';
for (let length = 12; length <= 32; length++) {
  const value = await generatePassword(site,seed,length);
  assert.equal(value.length,length,'Every supported length must be exact');
  assert.ok(categories.every(category => category.test(value)),'Every category must be present');
  assert.ok(value === await generatePassword(site,seed,length),'Matching inputs must be reproducible');
}
for (let i = 0; i < 256; i++) {
  const value = await generatePassword(site,seed + '-' + i,12);
  assert.ok(categories.every(category => category.test(value)),'Reserved positions preserve every required category');
}
const value = await generatePassword(site,seed,16);
assert.ok(value !== await generatePassword('another-site',seed,16),'The site separates generated values');
assert.ok(value !== await generatePassword(site,'another-seed',16),'The seed separates generated values');
assert.ok(value === await generatePassword(' SYNTHETIC-SITE ',' synthetic-seed ',16),'Input normalization stays stable');
// Synthetic outputs from the original local implementation; never print passwords.
const compatible = [
  [seed,12,'89bb505d576cea12dcab7bae34618eba2936376a0812eb5a3e01ee1087f6790d'],
  [seed,16,'787865b79b0c63b8fd5367812c83996f1367bc1f6fa712e6d7699b6d4b576bad'],
  [seed,32,'51093583bd9dbae945a6adc8b972b3f23907077f8f87cee8b6575389bce90535'],
  [seed + '-193',12,'7e0438f63a3dfaa1b23b4cea7fbb6418679c99c64d477289889b078ef1a2f7a1'],
];
for (const [input,length,expected] of compatible) {
  const output = await generatePassword(site,input,length);
  const digest = createHash('sha256').update(output).digest('hex');
  assert.equal(digest,expected,'Generated results remain compatible with the original local algorithm');
}
for (const length of [0,11,33,64,65,12.5,NaN,'16']) {
  await assert.rejects(generatePassword(site,seed,length),/12 到 32/);
}
for (const [badSite,badSeed] of [['',seed],[site,' '],[null,seed],[site,null]]) {
  await assert.rejects(generatePassword(badSite,badSeed,16),/平台名/);
}
console.log('password generator: exact lengths 12–32, four categories, original output compatibility, deterministic inputs and validation passed');
