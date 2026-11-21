#!/usr/bin/env python3
"""Apply AudioOneTap v1.7 speed and integrity fixes to the v1.6 source tree."""
from pathlib import Path

root = Path("app-project")
service = root / "app/src/main/java/com/onec/audio/AudioService.java"
transcoder = root / "app/src/main/java/com/onec/audio/AudioTranscoder.java"
activity = root / "app/src/main/java/com/onec/audio/MainActivity.java"
gradle = root / "app/build.gradle"

def change(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)

s = service.read_text()
s = change(s, 'import com.yausername.youtubedl_android.YoutubeDLRequest;',
           'import com.yausername.youtubedl_android.YoutubeDLRequest;\nimport com.yausername.youtubedl_android.YoutubeDLResponse;\nimport java.util.regex.Matcher;\nimport java.util.regex.Pattern;',
           'import response')
s = change(s, '            tryUpdateEngine();',
           '            // Never perform a network engine update in the download critical path.\n            // Keep the built-in verified extractor; refresh only in a separate maintenance release.',
           'remove costly auto update')
s = change(s,
    '''                    "ba[protocol*=m3u8]/ba",       // YTDLnis commonly offers itag 234 HLS audio
                    "ba[ext=webm]/ba",              // alternative Opus/WebM stream
                    "ba[protocol*=m3u8]/ba"        // alternate YouTube clients''',
    '''                    "ba[protocol!=m3u8][vcodec=none]/ba[protocol!=m3u8]", // direct-only first
                    "ba[protocol*=m3u8]/ba",       // HLS only when direct access fails
                    "ba[protocol*=m3u8]/ba"        // client fallback''',
    'direct stream priority')
s = change(s, '                request.addOption("--retries", "2");',
           '                request.addOption("--retries", "1");',
           'limit full restarts')
s = change(s, '                request.addOption("--fragment-retries", "2");',
           '''                request.addOption("--fragment-retries", "3");
                request.addOption("--concurrent-fragments", "6");
                request.addOption("--print", "after_move:AO_DURATION=%(duration)s");''',
           'fragment parallelism and source duration')
s = change(s,
           '''                String mode = attemptIndex == 0 ? "优先 HLS 音轨" :
                        (attemptIndex == 1 ? "改用 WebM/Opus 音轨" : "切换 YouTube 播放器客户端");''',
           '''                String mode = attemptIndex == 0 ? "直连音频流" :
                        (attemptIndex == 1 ? "并行下载分段音轨" : "切换 YouTube 播放器客户端");''',
           'updated UI mode')
s = change(s,
    '''                    YoutubeDL.getInstance().execute(request, processId, cb);
                    if (cancelled) throw new InterruptedException("用户已取消");
                    if (findAudio(attemptDir) == null) {
                        throw new IllegalStateException("下载结束但没有找到音频文件");
                    }
                    downloadDir = attemptDir;''',
    '''                    YoutubeDLResponse response = YoutubeDL.getInstance().execute(request, processId, cb);
                    if (cancelled) throw new InterruptedException("用户已取消");
                    File downloaded = findAudio(attemptDir);
                    if (downloaded == null || downloaded.length() < 1024) {
                        throw new IllegalStateException("下载结束但文件缺失或内容不足");
                    }
                    long declaredMs = expectedDurationMs(response.getOut());
                    long actualMs = AudioTranscoder.audioDurationMs(downloaded);
                    if (declaredMs >= 12000 && actualMs > 0
                            && actualMs + 2500 < declaredMs * 0.94) {
                        throw new IllegalStateException("音频不完整：原视频约 " +
                                (declaredMs / 1000) + " 秒，下载结果仅 " +
                                (actualMs / 1000) + " 秒");
                    }
                    downloadDir = attemptDir;''',
    'verify transfer duration')
s = change(s, '''                    if (cancelled) throw new InterruptedException("用户已取消");
                    lastDownloadError = error;''',
           '''                    if (cancelled) throw new InterruptedException("用户已取消");
                    lastDownloadError = error;''', 'noop identity') if False else s
s = change(s,
    '''    private File findAudio(File dir) {''',
    '''    private static long expectedDurationMs(String output) {
        if (output == null || output.isEmpty()) return 0;
        Matcher match = Pattern.compile("AO_DURATION=([0-9]+(?:\\\\.[0-9]+)?)").matcher(output);
        if (!match.find()) return 0;
        try {
            return Math.round(Double.parseDouble(match.group(1)) * 1000.0);
        } catch (NumberFormatException ignored) {
            return 0;
        }
    }

    private File findAudio(File dir) {''',
    'metadata parser')
s = change(s,
    '''        for (File f : files) {
            if (!f.isFile()) continue;
            String n = f.getName().toLowerCase(Locale.ROOT);
            if ((n.endsWith(".m4a") || n.endsWith(".webm") || n.endsWith(".opus")
                    || n.endsWith(".mp3") || n.endsWith(".mp4") || n.endsWith(".ogg")) && f.length() > 0) return f;
        }
        return null;''',
    '''        File largest = null;
        for (File f : files) {
            if (!f.isFile()) continue;
            String n = f.getName().toLowerCase(Locale.ROOT);
            if ((n.endsWith(".m4a") || n.endsWith(".webm") || n.endsWith(".opus")
                    || n.endsWith(".mp3") || n.endsWith(".mp4") || n.endsWith(".ogg"))
                    && f.length() > 1024 && (largest == null || f.length() > largest.length()))
                largest = f;
        }
        return largest;''',
    'reject tiny or invalid file and pick largest')
s = change(s,
    '''                if (fd == null || fd.getStatSize() == 0)
                    throw new IllegalStateException("已写入的音频无法再次读取");''',
    '''                if (fd == null || fd.getStatSize() != audio.length())
                    throw new IllegalStateException("保存后的文件大小与源音频不一致");''',
    'verify public save size')
service.write_text(s)

t = transcoder.read_text()
t = change(t,
    '''            if (target.length() < 128) throw new IOException("音频压缩结果为空");
            return target;''',
    '''            if (target.length() < 1024) throw new IOException("音频压缩结果为空");
            long sourceDuration = audioDurationMs(source);
            long outputDuration = audioDurationMs(target);
            if (sourceDuration >= 12000 && outputDuration > 0
                    && outputDuration + 2500 < sourceDuration * 0.94) {
                throw new IOException("32 kbps 压缩结果被截断：源音频 " +
                        sourceDuration / 1000 + " 秒，结果仅 " +
                        outputDuration / 1000 + " 秒");
            }
            return target;''',
    'transcode output duration check')
t = change(t,
    '''    private static ByteBuffer downmixToMono(ByteBuffer samples, int channels) throws IOException {''',
    '''    /** Read actual encoded audio duration without a second network request. */
    static long audioDurationMs(File input) {
        MediaExtractor scan = new MediaExtractor();
        try {
            scan.setDataSource(input.getAbsolutePath());
            for (int i = 0; i < scan.getTrackCount(); i++) {
                MediaFormat fmt = scan.getTrackFormat(i);
                String mime = fmt.getString(MediaFormat.KEY_MIME);
                if (mime == null || !mime.startsWith("audio/")) continue;
                if (fmt.containsKey(MediaFormat.KEY_DURATION)) {
                    long duration = fmt.getLong(MediaFormat.KEY_DURATION);
                    if (duration > 0) return duration / 1000L;
                }
                scan.selectTrack(i);
                long endUs = 0;
                for (int n = 0; n < 1000000; n++) {
                    long pts = scan.getSampleTime();
                    if (pts < 0) break;
                    endUs = pts;
                    if (!scan.advance()) break;
                }
                return endUs > 0 ? endUs / 1000L : 0;
            }
        } catch (Exception ignored) {
            return 0;
        } finally {
            scan.release();
        }
        return 0;
    }

    private static ByteBuffer downmixToMono(ByteBuffer samples, int channels) throws IOException {''',
    'audio duration reader')
transcoder.write_text(t)

a = activity.read_text()
a = change(a, 'label("音频直取 · 1.6",',
           'label("音频直取 · 1.7",', 'UI version')
a = change(a, '"音轨自动重试 · 32 kbps · 保存到 Drive"',
           '"优先直连 · 双重完整性校验 · 32 kbps · 保存到 Drive"', 'UI description')
activity.write_text(a)

g = gradle.read_text()
g = change(g, 'versionCode 7', 'versionCode 8', 'version code')
g = change(g, "versionName '1.6.0'", "versionName '1.7.0'", 'version name')
gradle.write_text(g)

print("Applied v1.7 hotfix: direct audio, faster segmented fallback, metadata/duration validation, no update before download.")
