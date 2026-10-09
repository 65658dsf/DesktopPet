// The sole derived action: mirror each gait frame, never reverse frame order.
const path = require('node:path');
const sharp = require(process.env.SHARP_MODULE || 'sharp');
async function main() {
  const folder = path.resolve(__dirname, '../../pets/qinche-q/animations');
  const input = path.join(folder, 'running-right.png');
  const {width, height} = await sharp(input).metadata();
  const layers = [];
  for(let index=0; index<8; index++) {
    const col=index%2, row=Math.floor(index/2);
    const left=Math.floor(col*width/2), top=Math.floor(row*height/4);
    const w=Math.floor((col+1)*width/2)-left, h=Math.floor((row+1)*height/4)-top;
    const frame=await sharp(input).extract({left,top,width:w,height:h}).flop().png().toBuffer();
    layers.push({input:frame,left,top});
  }
  const output=path.join(folder,'running-left.png');
  await sharp({create:{width,height,channels:4,background:'#00000000'}})
    .composite(layers).png().toFile(output);
  console.log(JSON.stringify({output,width,height,frames:8,order:'unchanged'}));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
