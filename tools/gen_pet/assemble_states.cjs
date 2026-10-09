/* Compose the compatibility atlas from QA exports of the actual native clips.
 * No generated artwork is synthesized or upscaled by this packaging step.
 * First run: python tools/preview_animation.py --all-states
 */
const fs = require('node:fs/promises');
const path = require('node:path');
const sharp = require(process.env.SHARP_MODULE || 'sharp');
const root = path.resolve(__dirname, '../..');
const states = ['idle', 'running-right', 'running-left', 'waving', 'jumping',
  'failed', 'waiting', 'running', 'review'];
const counts = [6, 8, 8, 4, 5, 8, 6, 6, 6];
const scale = process.argv.includes('--2x') ? 2 : 1;
const cellWidth = 192 * scale, cellHeight = 208 * scale;

async function main() {
  const layers = [];
  for (let row = 0; row < states.length; row++) {
    for (let index = 0; index < counts[row]; index++) {
      const input = path.join(root, 'build/qa-animation/all-states', states[row],
        'keyframes', `${String(index).padStart(2, '0')}.png`);
      const meta = await sharp(input).metadata();
      if (meta.width < cellWidth || meta.height < cellHeight) throw new Error(`Source too small: ${input}`);
      const frame = await sharp(input).resize(cellWidth, cellHeight, {kernel:'lanczos3'}).png().toBuffer();
      layers.push({input:frame, left:index * cellWidth, top:row * cellHeight});
    }
  }
  const output = path.join(root, 'pets/qinche-q', scale === 2 ? 'spritesheet@2x.webp' : 'spritesheet.webp');
  await sharp({create:{width:1536*scale,height:1872*scale,channels:4,background:'#00000000'}})
    .composite(layers).webp({lossless:true, effort:6}).toFile(output);
  const {data, info} = await sharp(output).ensureAlpha().raw().toBuffer({resolveWithObject:true});
  for (let row=0; row<9; row++) {
    for (let col=0; col<8; col++) {
      let occupied = 0;
      for (let y=row*cellHeight; y<(row+1)*cellHeight; y++) {
        for (let x=col*cellWidth; x<(col+1)*cellWidth; x++) {
          if (data[(y*info.width+x)*4+3] > 0) occupied++;
        }
      }
      if (col < counts[row] ? occupied === 0 : occupied !== 0)
        throw new Error(`Invalid atlas cell ${states[row]}:${col}`);
    }
  }
  console.log(JSON.stringify({output, width:info.width, height:info.height,
    states:states.length, frames:counts.reduce((a,b)=>a+b,0), unusedCellsTransparent:true}));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
