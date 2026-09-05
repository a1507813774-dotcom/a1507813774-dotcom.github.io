// Deployment refresh: Gemini direct API backend
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

export default async function handler(req, res) {
  cors(req, res);

  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return res.status(500).json({ error: 'Server GEMINI_API_KEY is not configured' });
  }

  const requiredToken = process.env.ANALYZE_TOKEN;
  if (requiredToken) {
    const supplied = req.headers['x-analyze-token'];
    if (!supplied || supplied !== requiredToken) {
      return res.status(401).json({ error: 'Invalid analysis access code' });
    }
  }

  try {
    const { image, prompt } = req.body || {};
    const parsed = parseDataUrl(image);
    if (!parsed || !parsed.mimeType.startsWith('image/')) {
      return res.status(400).json({ error: 'A base64 image data URL is required' });
    }
    if (image.length > 7_000_000) {
      return res.status(413).json({ error: 'Image is too large' });
    }

    const instruction = typeof prompt === 'string' && prompt.trim()
      ? prompt.trim()
      : '请简洁描述这张图片中最重要、最值得注意的信息。';

    const model = process.env.GEMINI_MODEL || 'gemini-3.5-flash-lite';
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
            { text: instruction }
          ]
        }],
        generationConfig: {
          temperature: 0.2,
          maxOutputTokens: 500
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
    return res.status(500).json({
      error: err?.message || 'Gemini analysis failed'
    });
  }
}
