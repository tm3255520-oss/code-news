/**
 * 快照存档 —— 趋势追踪的数据基础。
 *
 * 一次抓取只能看到「现在什么样」，连续的快照才能回答：涨粉速度、内容有没有在涨、
 * 哪条作品真的带来了增长。
 *
 * 用法:
 *   node snapshot.js --posts workdir/posts.json --dir snapshots/
 *
 * 设计要点：
 *  - 文件名带完整时间戳，同一天多次抓取不会互相覆盖
 *  - 存精简字段（不含 raw 大对象），否则几次快照就上百 MB
 *  - 同时存一份当时的 compute() 结果，趋势分析时不用重算
 */
const fs = require('fs');
const path = require('path');
const { compute, loadPosts } = require('./core');

function parseArgs() {
  const a = {};
  for (let i = 2; i < process.argv.length; i += 2) a[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
  return a;
}

const safe = (s) => String(s || 'unknown').replace(/[\\/:*?"<>|\s]+/g, '_').slice(0, 40);

(async () => {
  const args = parseArgs();
  if (!args.posts) { console.error('用法: --posts <posts.json> --dir <快照目录>'); process.exit(1); }
  const dir = args.dir || 'snapshots';
  fs.mkdirSync(dir, { recursive: true });

  const data = loadPosts(args.posts);
  const name = (data.account && data.account.name) || 'unknown';
  const now = new Date();
  const date = now.toISOString().slice(0, 10);
  const hm = now.toISOString().slice(11, 16).replace(':', '');

  // 只留趋势分析用得上的字段，raw 大对象不进快照
  const posts = data.posts.map((p) => ({
    id: p.id,
    create_time: p.create_time,
    title: String(p.title || '').slice(0, 120),
    digg: p.digg,
    comment: p.comment,
    share: p.share,
    collect: p.collect,
    play: p.play,
    media_type: p.media_type,
    media_count: p.media_count,
  }));

  const snap = {
    snapshot_date: date,
    captured_at: now.toISOString(),
    source_file: path.resolve(args.posts),
    platform: data.platform,
    account: data.account,
    post_count: posts.length,
    posts,
    metrics: compute(data),
    _unavailable: data._unavailable || [],
  };

  const file = path.join(dir, `${safe(data.platform)}__${safe(name)}__${date}T${hm}.json`);
  fs.writeFileSync(file, JSON.stringify(snap, null, 2), 'utf8');

  // 同一目录下是否已有该账号的更早快照
  const siblings = fs.readdirSync(dir).filter((f) => f.startsWith(`${safe(data.platform)}__${safe(name)}__`));

  console.log(`✅ 快照已存档: ${file}`);
  console.log(`   账号 ${name} | ${data.platform} | ${posts.length} 条 | 粉丝 ${(data.account && data.account.fans) || 0}`);
  console.log(`   该账号累计快照数: ${siblings.length}`);
  if (siblings.length === 1) {
    console.log('\n   ⚠️ 这是第 1 份快照，还看不出任何趋势。');
    console.log('      建议隔一段时间（如 7 天）再抓一次，之后就能用 trend.js 看了。');
  } else {
    console.log('   现在可以运行: node trend.js --dir ' + dir);
  }
  process.exit(0);
})().catch((e) => { console.error('ERR', e.message); process.exit(1); });
