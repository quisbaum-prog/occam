"""Offline, fixed-clock browser evidence; visual judgments remain human judgments."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from PIL import Image, ImageChops, ImageStat, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

SCREENSHOT_WAIT_MS = 300_000


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def difference(a, b):
    image = ImageChops.difference(Image.open(a).convert('RGB'), Image.open(b).convert('RGB'))
    return round(sum(ImageStat.Stat(image).mean) / 3, 6)


def stable(page, path):
    # Dynamic button labels are masked for Pause and Restart comparisons only.
    page.screenshot(path=str(path), animations='allow', timeout=SCREENSHOT_WAIT_MS, mask=[page.locator('button, [role="button"]')],
                    mask_color='#000000')


def buttons(page):
    controls = page.locator('button, [role="button"], input[type="button"]')
    result = {}
    for i in range(controls.count()):
        control = controls.nth(i)
        label = ' '.join(filter(None, (control.text_content() or '',
                        control.get_attribute('aria-label'), control.get_attribute('title'),
                        control.get_attribute('value'))))
        if re.search(r'pause|resume|play|fortsetzen|anhalten', label, re.I) and 'pause' not in result:
            result['pause'] = control
        if re.search(r'restart|reset|neustart|neu starten', label, re.I) and 'restart' not in result:
            result['restart'] = control
    return result


def checks(browser, source, output, viewport):
    context = browser.new_context(viewport=viewport, device_scale_factor=1,
                                  reduced_motion='no-preference', color_scheme='dark')
    page = context.new_page()
    errors, external = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    def route(request):
        url = request.request.url
        if url.startswith(('http:', 'https:', 'ws:', 'wss:')):
            external.append(url)
            request.abort()
        else:
            request.continue_()
    context.route('**/*', route)
    page.clock.install(time=0)
    page.clock.pause_at(0)
    page.goto(source.as_uri(), wait_until='load')
    stable(page, output / 'initial.png')
    page.clock.run_for(5000)
    stable(page, output / 'after-5s.png')
    motion = difference(output / 'initial.png', output / 'after-5s.png')
    controls = buttons(page)
    pause_ok, resume_ok, restart_ok = None, None, None
    if 'pause' in controls:
        controls['pause'].click(force=True, timeout=2000)
        stable(page, output / 'paused-0.png')
        page.clock.run_for(1000)
        stable(page, output / 'paused-1.png')
        pause_ok = difference(output / 'paused-0.png', output / 'paused-1.png') <= 0.05
        controls['pause'].click(force=True, timeout=2000)
        stable(page, output / 'resumed-0.png')
        page.clock.run_for(1000)
        stable(page, output / 'resumed-1.png')
        resume_ok = difference(output / 'resumed-0.png', output / 'resumed-1.png') > 0.05
    if 'restart' in controls:
        controls['restart'].click(force=True, timeout=2000)
        stable(page, output / 'restart-0.png')
        page.clock.run_for(1000)
        controls['restart'].click(force=True, timeout=2000)
        stable(page, output / 'restart-1.png')
        restart_ok = (difference(output / 'restart-0.png', output / 'restart-1.png') <= 0.05 and
                      difference(output / 'initial.png', output / 'restart-0.png') <= 0.05)
    fits = page.evaluate('document.documentElement.scrollWidth <= innerWidth && document.documentElement.scrollHeight <= innerHeight')
    result = {'page_errors': errors, 'external_requests': sorted(set(external)),
              'offline_load': not errors and not external,
              'motion_pixel_difference_5s': motion, 'motion_detected': motion > 0.05,
              'pause_control_found': 'pause' in controls, 'restart_control_found': 'restart' in controls,
              'pause_stable': pause_ok, 'resume_moves': resume_ok,
              'restart_reproducible': restart_ok, 'fits_viewport': fits,
              'interpretation': 'Pixel checks are evidence, not a visual score. Review false negatives manually.'}
    context.close()
    return result


def capture(source, output, config):
    started = time.monotonic()
    output.mkdir(parents=True)
    frames = output / 'frames'
    frames.mkdir()
    source = source.resolve()
    viewport, recording = config['viewport'], config['capture']
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--use-gl=angle', '--use-angle=swiftshader',
                                          '--enable-unsafe-swiftshader', '--disable-gpu-sandbox'])
        version = browser.version
        result = checks(browser, source, output, viewport)
        context = browser.new_context(viewport=viewport, device_scale_factor=1,
                                      reduced_motion='no-preference', color_scheme='dark')
        context.route('**/*', lambda route: route.abort() if route.request.url.startswith(('http:', 'https:')) else route.continue_())
        page = context.new_page()
        page.clock.install(time=0)
        page.clock.pause_at(0)
        page.goto(source.as_uri(), wait_until='load')
        count = recording['seconds'] * recording['fps']
        last_ms = 0
        for frame in range(count):
            target_ms = round(frame * 1000 / recording['fps'])
            if target_ms > last_ms:
                page.clock.run_for(target_ms - last_ms)
            last_ms = target_ms
            page.screenshot(path=str(frames / f'{frame:04d}.png'), animations='allow', timeout=SCREENSHOT_WAIT_MS)
            if frame == recording['screenshot_second'] * recording['fps']:
                shutil.copyfile(frames / f'{frame:04d}.png', output / 'screenshot.png')
        context.close()
        browser.close()
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                    '-framerate', str(recording['fps']), '-i', str(frames / '%04d.png'),
                    '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18',
                    '-movflags', '+faststart', str(output / 'clip.mp4')], check=True)
    # Frames are intermediate material; leave the evidence screenshots and final clip.
    for frame in frames.glob('*.png'):
        frame.unlink()
    frames.rmdir()
    result.update(chromium_version=version, viewport=viewport, renderer='swiftshader',
                  seconds=recording['seconds'], fps=recording['fps'],
                  rendering_wall_s=round(time.monotonic() - started, 3),
                  artifact_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  screenshot_wait_ms=SCREENSHOT_WAIT_MS,
                  capture_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    save(output / 'checks.json', result)
    print(json.dumps({'rendered': str(output), 'chromium': version}), flush=True)


def compose(run, output, config):
    output.mkdir(parents=True)
    blind_folder = output / 'blind'
    blind_folder.mkdir()
    manifest = json.loads((run / 'manifest.json').read_text(encoding='utf-8'))
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    font = ImageFont.truetype(font_path, 20)
    small = ImageFont.truetype(font_path, 17)
    width, height = 640, 400
    for repetition in range(1, manifest['repetitions'] + 1):
        rows = manifest['models']
        sheet = Image.new('RGB', (width * 3, (height + 90) * len(rows)), '#0a0a14')
        draw = ImageDraw.Draw(sheet)
        tiles = []
        blind = []
        for row, model in enumerate(rows):
            for col, arm in enumerate(('base', 'occam', 'ponytail')):
                cell = next((c for c in manifest['schedule'] if c['model'] == model['id'] and
                             c['effort'] == model['effort'] and c['arm'] == arm and
                             c['repetition'] == repetition), None)
                folder = run / 'cells' / cell['cell_id'] if cell else None
                x, y = col * width, row * (height + 90)
                label = f'{model["id"]} / {model["effort"]} | {arm}'
                draw.text((x + 16, y + 12), label, fill='white', font=font)
                if folder and (folder / 'result.json').exists():
                    result = json.loads((folder / 'result.json').read_text())
                    tokens = (result.get('usage') or {}).get('total_tokens', '?')
                    detail = f'{tokens} tokens | {result.get("generation_wall_s", "?")}s'
                else:
                    detail = 'Missing result'
                draw.text((x + 16, y + 45), detail, fill='#babac9', font=small)
                render = folder / 'render' if folder else None
                if render and (render / 'screenshot.png').exists():
                    sheet.paste(Image.open(render / 'screenshot.png').resize((width, height)), (x, y + 90))
                    clip = render / 'clip.mp4'
                    text = f'{label}\n{detail}'
                    label_file = output / f'label-{row}-{col}-r{repetition}.txt'
                    label_file.write_text(text, encoding='utf-8')
                    tile = output / f'tile-{row}-{col}-r{repetition}.mp4'
                    vf = (f'scale={width}:{height},pad={width}:{height+90}:0:90:color=0x0a0a14,'
                          f'drawtext=fontfile={font_path}:textfile={label_file}:fontcolor=white:fontsize=17:x=16:y=12')
                    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                                    '-i', str(clip), '-vf', vf, '-an', '-c:v', 'libx264',
                                    '-pix_fmt', 'yuv420p', str(tile)], check=True)
                    tiles.append(tile)
                    blind_id = cell['blind_id']
                    shutil.copyfile(render / 'screenshot.png', blind_folder / f'{blind_id}.png')
                    shutil.copyfile(clip, blind_folder / f'{blind_id}.mp4')
                    blind.append({'blind_id': blind_id, 'file': f'{blind_id}.png',
                                  'visual_scores': {'shadow_geometry': None, 'disk_and_lensing': None,
                                                    'color_and_structure': None, 'rotation': None,
                                                    'cinematic_quality': None},
                                  'requirements': {'centered_circular_shadow': None, 'shadow_size': None,
                                      'edge_on_disk': None, 'rim_and_both_lensing_arcs': None,
                                      'white_gold_to_orange': None, 'fixed_camera': None,
                                      'visible_rotation_by_5s': None}, 'notes': ''})
                else:
                    draw.text((x + 16, y + 170), 'No render available', fill='#ee9999', font=font)
        sheet.save(output / f'comparison-r{repetition}.png')
        if len(tiles) == 3 * len(rows):
            command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y']
            for tile in tiles:
                command.extend(['-i', str(tile)])
            layout = '|'.join(f'{(i%3)*width}_{(i//3)*(height+90)}' for i in range(len(tiles)))
            command.extend(['-filter_complex', f'xstack=inputs={len(tiles)}:layout={layout}',
                            '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                            str(output / f'comparison-r{repetition}.mp4')])
            subprocess.run(command, check=True)
        save(blind_folder / f'scorecard-r{repetition}.json', blind)
    print(json.dumps({'comparison_folder': str(output)}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['capture', 'compose', 'probe'])
    parser.add_argument('--source', type=Path, default=Path('/source/index.html'))
    parser.add_argument('--output', type=Path, default=Path('/home/bench/export'))
    parser.add_argument('--config', type=Path, default=Path('/input/benchmark.json'))
    parser.add_argument('--run', type=Path, default=Path('/run-data'))
    args = parser.parse_args()
    if args.mode == 'probe':
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            print(json.dumps({'chromium': browser.version}), flush=True)
            browser.close()
        return
    config = json.loads(args.config.read_text(encoding='utf-8'))
    if args.mode == 'capture':
        capture(args.source, args.output, config)
    else:
        compose(args.run, args.output, config)


if __name__ == '__main__':
    main()
