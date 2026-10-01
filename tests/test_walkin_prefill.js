// Exercise the actual vanilla JS with a tiny DOM stub; no server/network needed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const script = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');
const marker = 'function configureWalkinUserPrefill()';
assert(script.includes(marker));
const source = script.slice(script.indexOf(marker));
const names = ['first_name', 'last_name', 'birth_year', 'email', 'phone'];
const user = {first_name:'Anne', last_name:'TEST', birth_year:1990,
              email:'anne@example.invalid', phone:'0600000000'};
class Field {
  constructor() { this.current = ''; this.listeners = new Map(); }
  get value() { return this.current; }
  set value(value) { this.current = String(value); }
  addEventListener(name, callback) { this.listeners.set(name, callback); }
  fire(name) { return this.listeners.get(name)?.(); }
}
function fixture(fetcher = async () => ({ok:true, json:async () => user})) {
  const fields = new Map(names.map(name => [name, new Field()]));
  const select = new Field();
  const form = {querySelector:() => select, elements:{namedItem:name => fields.get(name)},
                dataset:{walkinPrefillUrl:'/admin/animations/1/inscriptions/usager/__PUBLIC_ID__'}};
  const requests = [];
  vm.runInNewContext(source, {document:{querySelector:() => form},
    fetch:(url,options) => {requests.push({url,options});return fetcher(url,options);}});
  return {fields,select,requests,choose:async value => {select.value=value;await select.fire('change');}};
}
function deferred() {
  let resolve;
  const promise = new Promise(value => {resolve=value;});
  return {resolve,promise};
}
(async () => {
  vm.runInNewContext(source, {document:{querySelector:() => null},fetch:() => assert.fail('No form, no fetch')});
  console.log('1. No form: no request');
  const filled = fixture();
  await filled.choose('1001');
  for (const name of names) assert.equal(filled.fields.get(name).value,String(user[name]));
  assert.equal(filled.requests[0].url,'/admin/animations/1/inscriptions/usager/1001');
  assert.equal(filled.requests[0].options.credentials,'same-origin');
  assert.equal(filled.requests[0].options.cache,'no-store');
  assert(!filled.requests[0].options.method); // Read only; never update the master record.
  console.log('2. Immediate prefill: five fields, authenticated read-only request');
  const email = filled.fields.get('email');
  email.value='voluntary@example.invalid';email.fire('input');
  await filled.choose('');
  assert.equal(email.value,'voluntary@example.invalid');
  for (const name of names.filter(name => name !== 'email')) assert.equal(filled.fields.get(name).value,'');
  console.log('3. Visitor: injected fields cleared, deliberate edits preserved');
  const edited = fixture();await edited.choose('1001');
  edited.fields.get('first_name').fire('input'); // User deliberately retained/retyped the same value.
  await edited.choose('');
  assert.equal(edited.fields.get('first_name').value,'Anne');
  console.log('4. Deliberate edit to the same value is also preserved');
  const late = deferred();const race = fixture(() => late.promise);
  const pending = race.choose('1001');
  await race.choose('');
  late.resolve({ok:true,json:async () => user});await pending;
  for (const name of names) assert.equal(race.fields.get(name).value,'');
  console.log('5. Late response cannot refill a deselected user');
  const ongoing = deferred();const typing = fixture(() => ongoing.promise);
  const loading = typing.choose('1001');
  typing.fields.get('email').value='typed@example.invalid';typing.fields.get('email').fire('input');
  ongoing.resolve({ok:true,json:async () => user});await loading;
  assert.equal(typing.fields.get('email').value,'typed@example.invalid');
  assert.equal(typing.fields.get('first_name').value,'Anne');
  console.log('6. Typing during the request is not overwritten');
  console.log('6 JavaScript tests passed');
})().catch(error => {console.error(error);process.exitCode=1;});
