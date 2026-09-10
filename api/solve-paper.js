// 项目：分支2｜整页试卷 Gemini 作答后端
// 作用：接收手机 A 截取的整页试卷图片，要求 Gemini 扫描所有可见题号、逐题作答，并返回“答案总览 + 详细解析 + 识别说明”。
// 版本：v2.1-branch2-full-paper-answer
// 修改日期：2026-09-10

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

const PAPER_PROMPT = `你是“整页试卷作答助手”。当前输入不是单独一道题，而可能是一整张试卷、练习卷或同一页上的多道题。

你的首要任务是：扫描图片中所有可见且属于试卷内容的题目与小问，并逐题作答。绝对不能只挑“最主要的一道题”。

扫描规则：
1. 按从上到下、从左到右的顺序检查整幅图片。
2. 识别并保留印刷出来的原题号，包括 1、2、3、(1)、(2)、①、② 等层级；子问应写成类似 12(1)、12(2)。
3. 图片中只要能看见一道题的题号，就要尽力处理；如果题干或选项不完整，不要省略该题，而要在答案处写“无法可靠识别”。
4. 不要大段转录题干，不要把整张卷子重新电子化。只有在题号无法辨认、需要区分题目时，才可附极短的关键词。
5. 选择题：写“题号. 选项字母（关键答案内容）”。
6. 填空题：写“题号. 填空内容”；有多个空按①②或(1)(2)分开。
7. 判断题：写“题号. 正确/错误”。
8. 计算题、简答题、实验题：先给最终答案，再在详细解析中给出足以核验的关键步骤/依据。
9. 不允许因为输出太长而只答前几题；应覆盖当前图片中所有可见题号。确实无法辨认的也必须列出来。
10. 若图片中存在答案、批注或手写痕迹，不要直接照抄作为结论，应独立判断。

必须严格按以下纯文本格式输出，不要使用 Markdown 表格，不要加其他前言：

【答案总览】
1. A（……）
2. C（……）
3(1). ……
3(2). ……
……
每一个可见题号都占一行。

【详细解析】
1. 答案：A（……）
解析：说明关键依据，简洁但可核验。
2. 答案：C（……）
解析：……
……
所有能够可靠作答的题都给解析；“无法可靠识别”的题说明具体模糊/缺失之处。

【识别说明】
共识别到：X 道题/小问。
无法可靠识别：列出题号；若全部清晰则写“无”。
`;

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
    if (image.length > 10_000_000) {
      return res.status(413).json({ error: 'Image is too large' });
    }

    const model = process.env.GEMINI_SOLVE_MODEL || process.env.GEMINI_MODEL || 'gemini-3.5-flash-lite';
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-goog-api-key': apiKey
      },
      body: JSON.stringify({
        contents: [{
          role: 'user',
          parts: [
            { inline_data: { mime_type: parsed.mimeType, data: parsed.data } },
            { text: PAPER_PROMPT }
          ]
        }],
        generationConfig: {
          temperature: 0.1,
          maxOutputTokens: 6000
        }
      })
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = data?.error?.message || `Gemini API HTTP ${response.status}`;
      return res.status(response.status).json({ error: message });
    }

    const text = (data?.candidates?.[0]?.content?.parts || [])
      .map(part => part?.text || '')
      .join('')
      .trim();

    return res.status(200).json({
      text: text || 'Gemini 没有返回文字结果',
      model
    });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ error: err?.message || 'Gemini paper solving failed' });
  }
}
