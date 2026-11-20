import { expect, it, vi } from 'vitest'
import { CameraSession, cameraErrorMessage } from './camera'

function fixture() {
  const track = Object.assign(new EventTarget(), { stop: vi.fn(), readyState: 'live' })
  const stream = { getTracks: () => [track], getVideoTracks: () => [track] } as unknown as MediaStream
  const video = { srcObject: null, play: vi.fn().mockResolvedValue(undefined) } as unknown as HTMLVideoElement
  const getUserMedia = vi.fn().mockResolvedValue(stream)
  return { track, stream, video, getUserMedia, devices: { getUserMedia } as unknown as MediaDevices }
}

it('opens the selected source and stops every track when the page leaves', async () => {
  const { track, video, stream, devices, getUserMedia } = fixture()
  const camera = new CameraSession()
  const disconnected = vi.fn()
  await expect(camera.start(devices, video, 'camera-a', disconnected)).resolves.toBe(true)
  expect(getUserMedia).toHaveBeenCalledWith({ video: { deviceId: { exact: 'camera-a' } }, audio: false })
  expect(video.srcObject).toBe(stream)
  camera.stop()
  expect(track.stop).toHaveBeenCalledOnce()
  expect(video.srcObject).toBeNull()
  track.dispatchEvent(new Event('ended'))
  expect(disconnected).not.toHaveBeenCalled()
})

it('disposes a stream that arrives after Stop while permission was pending', async () => {
  const { track, video, stream, devices, getUserMedia } = fixture()
  let grant!: (stream: MediaStream) => void
  getUserMedia.mockReturnValueOnce(new Promise<MediaStream>((resolve) => { grant = resolve }))
  const camera = new CameraSession()
  const starting = camera.start(devices, video, '', vi.fn())
  camera.stop()
  grant(stream)
  await expect(starting).resolves.toBe(false)
  expect(track.stop).toHaveBeenCalledOnce()
  expect(video.play).not.toHaveBeenCalled()
})

it('clears a disconnected camera and lets the user reconnect', async () => {
  const first = fixture()
  const second = fixture()
  const camera = new CameraSession()
  const disconnected = vi.fn()
  await camera.start(first.devices, first.video, '', disconnected)
  first.track.dispatchEvent(new Event('ended'))
  expect(disconnected).toHaveBeenCalledOnce()
  expect(first.video.srcObject).toBeNull()
  await expect(camera.start(second.devices, second.video, 'replacement', disconnected)).resolves.toBe(true)
  camera.stop()
  expect(second.track.stop).toHaveBeenCalledOnce()
})

it('reports denied permissions and missing cameras without attaching a stream', async () => {
  const { video, devices, getUserMedia } = fixture()
  const camera = new CameraSession()
  for (const [name, message] of [['NotAllowedError', 'permission was denied'], ['NotFoundError', 'camera is unavailable']]) {
    const error = new DOMException('', name)
    getUserMedia.mockRejectedValueOnce(error)
    await expect(camera.start(devices, video, '', vi.fn())).rejects.toBe(error)
    expect(cameraErrorMessage(error)).toContain(message)
    expect(video.srcObject).toBeNull()
  }
})
