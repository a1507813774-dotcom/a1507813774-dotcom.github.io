import OpenAI from 'openai';

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

export default async function handler(req, res) {
  cors(req, res);

  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const gatewayToken = process.env.AI_GATEWAY_API_KEY || process.env.VERCEL_OIDC_TOKEN;
  if (!gatewayToken) {
    return res.status(500).json({ error: 'Vercel AI Gateway authentication is unavailable' });
  }

  const requiredToken = process.env.ANALYZE_TOKEN;
  if (requiredToken) {
    const supplied = req.headers['x-analyze-token'];
    if (!supplied || supplied !== requiredToken) {
      return res.status(401).json({ error: 'Invalid analysis access code' });
    }
  }

  try {
    const { image, prompt, detail = 'low' } = req.body || {};
    if (typeof image !== 'string' || !image.startsWith('data:image/')) {
      return res.status(400).json({ error: 'A base64 image data URL is required' });
    }
    if (image.length > 7_000_000) {
      return res.status(413).json({ error: 'Image is too large' });
    }

    const instruction = typeof prompt === 'string' && prompt.trim()
      ? prompt.trim()
      : '请简洁描述这张图片中最重要、最值得注意的信息。';

    const model = process.env.AI_VISION_MODEL || 'openai/gpt-4.1-mini';
    const client = new OpenAI({
      apiKey: gatewayToken,
      baseURL: 'https://ai-gateway.vercel.sh/v1'
    });

    const response = await client.responses.create({
      model,
      input: [
        {
          role: 'user',
          content: [
            { type: 'input_text', text: instruction },
            {
              type: 'input_image',
              image_url: image,
              detail: ['low', 'high', 'auto'].includes(detail) ? detail : 'low'
            }
          ]
        }
      ],
      max_output_tokens: 600
    });

    return res.status(200).json({
      text: response.output_text || '',
      model,
      response_id: response.id
    });
  } catch (err) {
    console.error(err);
    return res.status(500).json({
      error: err?.message || 'AI analysis failed'
    });
  }
}
