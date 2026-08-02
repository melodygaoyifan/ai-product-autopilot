# Building and testing a 小程序 with `avs`

The end-to-end pipeline for WeChat mini-programs, and the reasons each rung
exists. Every rung below was added because the rung above it passed while
the product was broken — that is the only justification any of them have.

## The four rungs

| # | Rung | Runs where | Catches |
|---|---|---|---|
| 1 | Unit tests (`node --test`) | anywhere, CI | pure logic: cart totals, countdown maths, review validation |
| 2 | Loadability gate (`_miniprogram_gate`, automatic in the build loop) | anywhere, CI | the project would not open: no `app.json`/`app.js`, registered pages with no files, pages on disk nobody registered, **require chains that do not resolve inside `miniprogramRoot`** |
| 3 | Runtime check (`avs mp-runtime`) | macOS/Windows with DevTools, **never CI** | pages that open but render nothing; per-page screenshots as evidence |
| 4 | Designed-flow script (per product, over the same protocol) | same as 3 | the product does not do what the FDR says |

Rungs 1–2 are mechanical and cost nothing; run them always. Rung 3 needs
the desktop app and a one-time human toggle. Rung 4 is written per product
because only the product's own FDR says what "correct" means.

## Rung 2: the require scan

A module that fails to resolve throws at evaluation time, so the page's
`Page()` never registers and the page renders **pure white** — while
DevTools opens the project happily and every page *file* exists. Shipped
exactly that way once: `utils/telemetry.js` written at the repo root
(outside `miniprogramRoot`), imported by three pages via three different
relative paths. 3 of 7 pages blank, every gate green.

The gate now walks relative `require()`/`import` chains from `app.js` and
every registered page and fails on two shapes: a specifier that resolves
to no file, and one that escapes `miniprogramRoot` (DevTools cannot
package what is outside the root). Bare npm names are out of scope —
`miniprogram_npm/` is a build step this gate cannot see.

## Rung 3: `avs mp-runtime`

```
avs mp-runtime --repo-dir /path/to/workspace
```

Per page: `reLaunch` → screenshot → verdict. Screenshots land in
`.mas/mp-runtime/`; the CLI's own output lands in
`.mas/mp-runtime/cli-auto.log`.

**A page counts as broken when its screenshot is a single flat color.**
"reLaunch did not throw" is not evidence — a page whose JS threw before
`Page()` still relaunches and still sits on the page stack. The pixels are
the judge, and they are cause-agnostic: a blank page fails whether the
cause was a bad require, an empty WXML, or a template that rendered
nothing.

Preconditions, each a **visible skip naming its remedy** — never a silent
pass, because "no check ran" and "the pages render" must never look alike:

| Missing | What you see |
|---|---|
| DevTools not installed | skip; says it is macOS/Windows-only and can never run in CI |
| `node` absent | skip |
| `miniprogram-automator` absent | skip naming `npm i -D miniprogram-automator` |
| service port off | skip naming Settings → Security → Service Port (设置 → 安全设置 → 服务端口) |
| `app.json` registers no pages | skip; rung 2 already blocks on this |

### Why it does not use `miniprogram-automator` to drive

Both `launch()` and `connect()` hang indefinitely, with no diagnosis,
against IDE `2.01.2510290` — while the raw protocol on the same port
answers in milliseconds. The package is still the documented install
(its `ws` dependency is what the driver imports), but the driver speaks
the protocol itself: `Tool.getInfo`, `App.callWxMethod` (`reLaunch`),
`App.captureScreenshot`, `App.enableLog` → `App.logAdded`.

The check spawns its own `cli auto` on a free port in 9420–9439 and
terminates it in a `finally`. It never reuses a listening port: a leftover
session serves whatever project *it* opened, and reusing one once verified
the wrong app under this project's name — every page "rendered", none of
them ours.

### Operational notes (macOS, verified)

- **Zombie sessions block later runs.** A killed driver can leave
  `cli auto` alive; it queue-blocks the next handshake. `pkill -f "cli auto"`.
- **Cold boots are slow.** A brand-new project window takes 60–150s to
  compile and bind its port. Start the IDE first (`open -a wechatwebdevtools`)
  and wait for `Default/.ide` to appear under the IDE's per-account support
  directory.
- **The IDE degrades over a long automation session.** After many
  open/relaunch cycles, `App.captureScreenshot` starts timing out and app
  calls begin failing with bare `Uncaught [object Object]` — on a project
  that passes cleanly after a full quit and relaunch. If a run that used to
  be green starts failing in the driver rather than in the assertions, quit
  the IDE completely (`pkill -f wechatwebdevtools`), confirm no `94xx` port
  is still held, and cold-start before concluding the product broke.
  Corollary for anything you write on this protocol: **treat screenshots as
  best-effort**, never as a step that can abort the run.
- **First open of a new project is very slow, and it is not a
  misconfiguration.** DevTools compiles a project it has never seen from
  scratch: measured here, the first open exceeded 300s while `cli auto`
  printed its success marker, and the port bound only after the wait — the
  second run took **27s**. The skip message distinguishes the two cases by
  reading the CLI's log, so a first-open timeout does not send you to
  re-check a service-port toggle that is already on. Re-run.
- **`libVersion: "latest"` is fine** — tested both ways on a cold IDE, with
  identical results. It breaks `miniprogram-automator` (whose `checkVersion`
  compares an undefined `SDKVersion`) but not the raw driver, which never
  version-checks. Pinning is a workaround for a client this pipeline no
  longer uses; do not cargo-cult it.
- The service port is a security setting on someone's machine. The
  framework names it and stops; it does not flip it for you.

## Rung 4: the designed-flow script

Rung 3 proves the pages render. Only a per-product script proves the
product *works*. Drive the same protocol and assert against the FDR:

```js
const evl = async (fn, ...args) =>
  (await send('App.callFunction', { functionDeclaration: fn, args })).result;
const pageData   = () => evl('function(){var s=getCurrentPages(); return s[s.length-1].data}');
const callHandler = (n, a) => evl(
  'function(n,a){var s=getCurrentPages(); var p=s[s.length-1]; p[n](a); return true}', n, a);
```

With those three primitives plus `App.mockWxMethod` (for
`getUserProfile`-class dialogs, which no automation can click) and
`wx.setStorageSync`/`removeStorageSync` through `evl` (to seed and clear
state), a full acceptance pass is a flat list of `check(label, condition)`
lines. The avs-studio-3 script covers 17: cached shelf on the home page,
add-to-cart, an order refused without an address, the 24h countdown
reading from `placedAt` rather than open time, per-product reviews with
threaded replies, profile save, share data.

Two failures it caught that every other rung passed: `buildOrder` never
wrote `placedAt`, so every fresh order showed `00:00:00` and could never
deliver; and the home page was a stub bound to an empty `{{title}}`.

## Order of work

1. `avs build` — the loop runs rungs 1–2 itself and will not save code that
   would not load.
2. `avs mp-runtime` — once, after the build, on your own machine. Look at
   the screenshots; the tool's verdict is a floor, not a ceiling.
3. Write the flow script for the product's own FDR. It is the only rung
   that knows what the product is supposed to do.
