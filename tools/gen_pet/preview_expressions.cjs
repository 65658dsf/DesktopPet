// Assemble real Qt render exports; no source artwork is redrawn.
// First: .venv/Scripts/python.exe tools/preview_animation.py [--poke|--all-states]
// Then: node tools/gen_pet/preview_expressions.cjs [--poke|--all-states]
// Requires sharp; optional SHARP_MODULE selects a bundled dependency.
const path = require('node:path');
const fs = require('node:fs');
const sharp = require(process.env.SHARP_MODULE || 'sharp');
const root = path.resolve(__dirname, '../..');
const poke = process.argv.includes('--poke');
const allStates = process.argv.includes('--all-states');
if (poke && allStates) throw new Error('--poke and --all-states are mutually exclusive');
const background = '#211b23';
const xml = value => String(value).replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;'
})[char]);

function readFrames(source) {
  const frames = JSON.parse(fs.readFileSync(path.join(source, 'frames.json'), 'utf8'));
  if (!frames.length) throw new Error(`No frames in ${source}`);
  return frames.map(frame => ({...frame, delay: Math.max(20, Math.round(frame.delay / 10) * 10)}));
}

async function encodeGif(source, target) {
  const manifest = readFrames(source);
  const size = await sharp(path.join(source, manifest[0].file)).metadata();
  const frames = [];
  for (const frame of manifest) {
    frames.push(await sharp(path.join(source, frame.file))
      .flatten({background}).ensureAlpha().raw().toBuffer());
  }
  await sharp(Buffer.concat(frames), {
    raw: {width: size.width, height: size.height * frames.length, channels: 4, pageHeight: size.height}
  }).gif({delay: manifest.map(frame => frame.delay), loop: 0, effort: 4, colours: 256}).toFile(target);
  console.log(target);
  return manifest;
}

async function renderAllStates() {
  const source = path.join(root, 'build/qa-animation/all-states');
  const manifest = JSON.parse(fs.readFileSync(path.join(source, 'manifest.json'), 'utf8'));
  const states = manifest.states;
  if (states.length !== 9) throw new Error(`Expected nine states, found ${states.length}`);
  const width = 624, header = 62, tileWidth = 208, tileHeight = 252, height = header + tileHeight * 3 + 26;
  const spriteWidth = 192, spriteHeight = 208;
  const position = index => ({left: (index % 3) * tileWidth + 8,
    top: header + Math.floor(index / 3) * tileHeight + 4});
  const labels = states.map((entry, index) => {
    const {left, top} = position(index);
    return `<rect x="${left}" y="${top}" width="192" height="240" rx="14" fill="#2b222c"/>`
      + `<text x="${left + 96}" y="${top + 224}" text-anchor="middle" font-size="15">${xml(entry.label)}</text>`;
  }).join('');
  const backdrop = await sharp(Buffer.from(`<svg width="${width}" height="${height}" xmlns="http://www.w3.org/2000/svg">`
    + `<rect width="100%" height="100%" fill="${background}"/>`
    + '<g font-family="Microsoft YaHei, sans-serif" fill="#f4e8ef">'
    + `<text x="18" y="28" font-size="21" font-weight="600">${xml(manifest.pet)} · 动作总览</text>`
    + '<text x="18" y="49" font-size="12" fill="#c2acba">实际播放节奏 · 原生动作帧与短过渡</text>'
    + labels
    + `<text x="18" y="${height - 10}" font-size="11" fill="#b4a0ae">随机停留采用区间中值；各状态按自身节奏独立循环。</text></g></svg>`)).png().toBuffer();
  const resizedFrames = [];
  for (const state of states) {
    const directory = path.join(source, state.directory);
    const frames = await encodeGif(directory, path.join(directory, 'preview.gif'));
    let elapsed = 0;
    const sequence = [];
    for (const frame of frames) {
      sequence.push({start: elapsed, delay: frame.delay,
        image: await sharp(path.join(directory, frame.file)).resize(spriteWidth, spriteHeight).png().toBuffer()});
      elapsed += frame.delay;
    }
    resizedFrames.push({duration: elapsed, frames: sequence});
  }

  // Use the union of all frame boundaries. Long holds remain single GIF frames
  // while each tile retains its own actual cycle length and short transitions.
  const duration = Math.max(...resizedFrames.map(sequence => sequence.duration));
  const moments = new Set([0, duration]);
  for (const sequence of resizedFrames) {
    for (let cycle = 0; cycle < duration; cycle += sequence.duration) {
      for (const frame of sequence.frames) {
        if (cycle + frame.start < duration) moments.add(cycle + frame.start);
      }
    }
  }
  const timeline = [...moments].sort((a, b) => a - b);
  const composites = [];
  const delays = [];
  for (let i = 0; i < timeline.length - 1; i++) {
    const layers = resizedFrames.map((sequence, index) => {
      const moment = timeline[i] % sequence.duration;
      const frame = sequence.frames.findLast(frame => frame.start <= moment);
      return {input: frame.image, ...position(index)};
    });
    composites.push(await sharp(backdrop).composite(layers).ensureAlpha().raw().toBuffer());
    delays.push(timeline[i + 1] - timeline[i]);
  }
  const preview = path.join(root, 'pets/qinche-q/animations/all-states-preview.gif');
  await sharp(Buffer.concat(composites), {
    raw: {width, height: height * composites.length, channels: 4, pageHeight: height}
  }).gif({delay: delays, loop: 0, effort: 4, colours: 256}).toFile(preview);
  console.log(`${preview} (${composites.length} frames, ${duration}ms)`);

  const contactLayers = [];
  for (let index = 0; index < states.length; index++) {
    const state = states[index];
    const pose = state.poses[Math.floor(state.poses.length / 2)];
    contactLayers.push({input: await sharp(path.join(source, state.directory, pose.file))
      .resize(spriteWidth, spriteHeight).png().toBuffer(), ...position(index)});
  }
  const contact = path.join(source, 'contact-sheet.png');
  await sharp(backdrop).composite(contactLayers).png().toFile(contact);
  console.log(contact);

  const cards = states.map(state => `<article><img src="${xml(state.directory)}/preview.gif" alt="${xml(state.label)} 动画">`
    + `<h2>${xml(state.label)} <small>${xml(state.state)}</small></h2>`
    + `<p>${state.poses.length} 个动作帧 · ${(state.durationMs / 1000).toFixed(2)} 秒一轮</p></article>`).join('\n');
  const html = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
    + `<title>${xml(manifest.pet)} · 动作预览</title><style>`
    + ':root{color-scheme:dark;font-family:"Microsoft YaHei",sans-serif;background:#211b23;color:#f4e8ef}'
    + 'body{max-width:1080px;margin:28px auto;padding:0 20px}h1{font-size:26px}p{color:#c2acba}'
    + 'main{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:18px}'
    + 'article{background:#2b222c;border-radius:18px;padding:12px;text-align:center}'
    + 'img{display:block;width:100%;max-width:384px;aspect-ratio:192/208;object-fit:contain;margin:auto}'
    + 'h2{font-size:18px;margin:4px 0}small{font-size:12px;color:#c2acba;font-weight:400}article p{font-size:13px}'
    + '@media(prefers-reduced-motion:reduce){p.motion:after{content:" 可在桌宠设置中启用减少动态效果。"}}'
    + '</style><body>'
    + `<h1>${xml(manifest.pet)} · 动作预览</h1>`
    + '<p class="motion">九种状态按实际播放速度独立循环。随机停留采用区间中值。</p>'
    + `<main>${cards}</main></body></html>`;
  fs.writeFileSync(path.join(source, 'index.html'), html, 'utf8');
  console.log(path.join(source, 'index.html'));
}

(async () => {
  if (allStates) return renderAllStates();
  const source = path.join(root, 'build/qa-animation', poke ? 'poke' : 'smooth');
  const target = path.join(root, 'pets/qinche-q/animations', poke ? 'poke-preview.gif' : 'preview.gif');
  await encodeGif(source, target);
})().catch(error => {console.error(error); process.exitCode = 1;});
