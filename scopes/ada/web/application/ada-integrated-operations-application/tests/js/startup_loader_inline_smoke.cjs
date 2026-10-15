const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { spawnSync } = require('node:child_process');

const source = path.resolve(__dirname,
    '../../src/ada/web/application/integrated_operations/modules/dashboard/startup.py');
const extract = String.raw`
import ast, pathlib
source = pathlib.Path(__import__('sys').argv[1]).read_text()
tree = ast.parse(source)
index = next(node for node in tree.body if isinstance(node, ast.Assign) and any(getattr(x, 'id', '') == 'STARTUP_LOADER_INDEX' for x in node.targets))
fragments = next(kw.value for kw in index.value.keywords if kw.arg == 'body_start_fragments')
items = eval(compile(ast.Expression(fragments), '<startup>', 'eval'), {'DEFAULT_OPERATIONAL_BRAND_LOGO_SRC': '/test.svg'})
print(items[1][len('<script>'):-len('</script>')])
`;
const result = spawnSync(process.env.PYTHON || 'python3', ['-c', extract, source], {
    encoding: 'utf8',
});
assert.equal(result.status, 0, result.stderr);
const script = result.stdout.trim();
assert.ok(script);

function run(pathname, expectedTimeout = 14500) {
    const timers = [];
    let removed = false;
    const attributes = {};
    const classes = new Set();
    const overlay = {
        classList: { add: (value) => classes.add(value) },
        setAttribute: (name, value) => { attributes[name] = value; },
        remove: () => { removed = true; },
    };
    const document = {
        documentElement: { dataset: {} },
        getElementById: (id) => id === 'ada-io-startup-loader' ? overlay : null,
    };
    const warnings = [];
    const window = {
        setTimeout: (fn, ms) => { timers.push({ fn, ms }); },
        adaIoStartupPending: () => ['area_2', 'alarms_render'],
    };
    vm.runInNewContext(script, {
        document, window, location: { pathname },
        console: { warn: (...args) => warnings.push(args) },
    });
    if (pathname !== '/') {
        assert.equal(document.documentElement.dataset.adaIoLoaderSkip, 'true');
        assert.equal(timers.length, 0);
        return;
    }
    assert.equal(document.documentElement.dataset.adaIoLoaderActive, 'true');
    assert.equal(timers.shift().ms, expectedTimeout);
    const timeout = window.adaIoFinishStartupLoader;
    timeout('timeout');
    assert.equal(warnings.length, 1);
    assert.ok(classes.has('ada-io-startup-loader--exit'));
    assert.equal(attributes['aria-hidden'], 'true');
    assert.equal(document.documentElement.dataset.adaIoLoaderActive, 'true');
    const fade = timers.shift();
    assert.equal(fade.ms, 500);
    fade.fn();
    assert.equal(removed, true);
    assert.equal(document.documentElement.dataset.adaIoLoaderActive, undefined);
    timeout('ready');
    assert.equal(warnings.length, 1);
}
run('/');
run('/manager');
console.log('Startup loader timeout and scroll restore: OK');
