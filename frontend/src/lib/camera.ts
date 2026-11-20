export class CameraSession {
  private generation = 0
  private stream?: MediaStream
  private video?: HTMLVideoElement
  private onEnded?: () => void

  stop() {
    this.generation += 1
    for (const track of this.stream?.getTracks() ?? []) {
      if (this.onEnded) track.removeEventListener('ended', this.onEnded)
      track.stop()
    }
    if (this.video) this.video.srcObject = null
    this.stream = undefined
    this.video = undefined
    this.onEnded = undefined
  }

  async start(devices: MediaDevices, video: HTMLVideoElement, deviceId: string, disconnected: () => void) {
    this.stop()
    const generation = this.generation
    try {
      const stream = await devices.getUserMedia({
        video: deviceId ? { deviceId: { exact: deviceId } } : { facingMode: { ideal: 'environment' } },
        audio: false,
      })
      if (generation !== this.generation) {
        stream.getTracks().forEach((track) => track.stop())
        return false
      }
      this.stream = stream
      this.video = video
      this.onEnded = () => {
        if (generation !== this.generation) return
        this.stop()
        disconnected()
      }
      for (const track of stream.getVideoTracks()) {
        track.addEventListener('ended', this.onEnded)
        if (track.readyState === 'ended') {
          this.onEnded()
          return false
        }
      }
      video.srcObject = stream
      await video.play()
      return generation === this.generation
    } catch (error) {
      if (generation !== this.generation) return false
      this.stop()
      throw error
    }
  }
}

export function cameraErrorMessage(error: unknown) {
  const name = error instanceof Error ? error.name : ''
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return 'Camera permission was denied. Allow access in browser settings, then reconnect.'
  }
  if (name === 'NotFoundError' || name === 'OverconstrainedError') {
    return 'The selected camera is unavailable. Connect a camera or choose another source.'
  }
  return 'The camera could not start. Check that it is connected and available, then reconnect.'
}
