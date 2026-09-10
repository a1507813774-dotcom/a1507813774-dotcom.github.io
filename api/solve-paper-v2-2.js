// 项目：分支2｜整页试卷 Gemini 仅答案后端
// 作用：扫描整页试卷的全部可见题号，只返回“题号 + 答案”，并尽量转换成普通人可直接阅读的数学/物理符号。
// 版本：v2.2-branch2-answer-only
// 修改日期：2026-09-10
// 基础版本：v2.1-branch2-full-paper-answer

function cors(req, res) {
  const origin = req.headers.origin || '';
  const allowed = ['https://a1507813774-dotcom.github.io'];
  if (origin && (allowed.includes(origin) || origin.endsWith('.vercel.app'))) {
    res.setHeader('Access-Control-Allow-Origin', origin);
  }
  res.setHeader('Vary', 'Origin');
  res.setHeader('Access-Control-Allow-Methods', 'POST,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type,X-Analyze-Token');
}

function parseDataUrl(dataUrl) {
  const match = /^data:([^;]+);base64,(.+)$/s.exec(dataUrl || '');
  if (!match) return null;
  return { mimeType: match[1], data: match[2] };
}

const PAPER_PROMPT = `你是“整页试卷答案助手”。输入可能是一整张试卷或一整页多道题。

任务：
1. 从上到下、从左到右扫描图片中全部可见题目和小问，不能只答一道。
2. 保留原题号和小问编号，例如：1、2、3(1)、3(2)、①、②。
3. 每一个能看到的题号都必须占一行。能可靠作答就给答案；看不清或信息不足就写“无法可靠识别”。
4. 只给答案，不抄题干，不写解析，不写计算过程，不写识别说明，不加前言和结语。
5. 选择题格式示例：1. A；如果有必要可写 1. A（氧气）。
6. 填空/简答/计算题直接写最终答案。
7. 如果同一题有多个空或小问，分别保留编号。
8. 若图片中已有手写答案或批注，不要照抄，要独立判断。

符号规则非常重要：
- 输出必须是普通人直接阅读的文字和数学/物理符号。
- 禁止 LaTeX，禁止任何反斜杠命令，禁止 Markdown 代码形式。
- 禁止出现 \\text、\\times、\\frac、\\circ、\\cdot、^2、^3 等计算机排版代码。
- 应使用：×、÷、√、≤、≥、≈、≠、±、°、℃、Ω、π、²、³、Δ 等正常符号。
- 例如写“68 mm²”，不要写“68\\text{ mm}^2”。
- 例如写“0.8 × 2000 W × 4 s = 6400 J”，不要写 LaTeX。
- 分数可以写成“1/2”；平方根写“√2”或“√(a+b)”。

严格输出：
【答案】
1. ...
2. ...
3(1). ...
3(2). ...
……
除此之外不要输出任何内容。`;

const SUB = {'0':'₀','1':'₁','2':'₂','3':'₃','4':'₄','5':'₅','6':'₆','7':'₇','8':'₈','9':'₉'};

function humanizeNotation(input) {
  let s = String(input || '');
  s = s.replace(/```/g, '').replace(/\$\$/g, '').replace(/\$/g, '');
  for (let i = 0; i < 4; i++) {
    s = s.replace(/\\(?:text|mathrm|operatorname)\{([^{}]*)\}/g, '$1');
    s = s.replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, '($1)/($2)');
    s = s.replace(/\\sqrt\{([^{}]+)\}/g, '√($1)');
  }
  const map = [
    [/\\times/g,'×'], [/\\div/g,'÷'], [/\\cdot/g,'·'], [/\\circ/g,'°'],
    [/\\leq?/g,'≤'], [/\\geq?/g,'≥'], [/\\neq/g,'≠'], [/\\approx/g,'≈'],
    [/\\pm/g,'±'], [/\\Omega/g,'Ω'], [/\\pi/g,'π'], [/\\Delta/g,'Δ']
  ];
  for (const [re, v] of map) s = s.replace(re, v);
  s = s.replace(/\^\{?2\}?/g,'²').replace(/\^\{?3\}?/g,'³');
  s = s.replace(/([A-Za-z])_\{?([0-9])\}?/g, (_, a, b) => a + (SUB[b] || b));
  s = s.replace(/\\,/g,' ').replace(/\\;/g,' ').replace(/\\!/g,'');
  s = s.replace(/[{}]/g,'').replace(/\*\*/g,'').replace(/`/g,'');
  s = s.replace(/[ \t]+/g,' ').replace(/ *\n */g,'\n').replace(/\n{3,}/g,'\n\n').trim();
  return s;
}

export default async function handler(req, res) {
  cors(req, res);
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) return res.status(500).json({ error: 'Server GEMINI_API_KEY is not configured' });

  const requiredToken = process.env.ANALYZE_TOKEN;
  if (requiredToken) {
    const supplied = req.headers['x-analyze-token'];
    if (!supplied || supplied !== requiredToken) return res.status(401).json({ error: 'Invalid analysis access code' });
  }

  try {
    const { image } = req.body || {};
    const parsed = parseDataUrl(image);
    if (!parsed || !parsed.mimeType.startsWith('image/')) {
      return res.status(400).json({ error: 'A base64 image data URL is required' });
    }
    if (image.length > 10_000_000) return res.status(413).json({ error: 'Image is too large' });

    const model = process.env.GEMINI_SOLVE_MODEL || process.env.GEMINI_MODEL || 'gemini-3.5-flash-lite';
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {'Content-Type':'application/json','x-goog-api-key':apiKey},
      body: JSON.stringify({
        contents: [{role:'user',parts:[
          {inline_data:{mime_type:parsed.mimeType,data:parsed.data}},
          {text:PAPER_PROMPT}
        ]}],
        generationConfig:{temperature:0.05,maxOutputTokens:3500}
      })
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = data?.error?.message || `Gemini API HTTP ${response.status}`;
      return res.status(response.status).json({ error: message });
    }

    const raw = (data?.candidates?.[0]?.content?.parts || []).map(p => p?.text || '').join('').trim();
    const text = humanizeNotation(raw || 'Gemini 没有返回文字结果');
    return res.status(200).json({text,model});
  } catch (err) {
    console.error(err);
    return res.status(500).json({error:err?.message || 'Gemini paper solving failed'});
  }
}
