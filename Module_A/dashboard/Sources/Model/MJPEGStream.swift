import Foundation
import os

/// Reads a `multipart/x-mixed-replace` MJPEG stream (the mission UI's /stream.mjpg or the drone's web_video_server)
/// and yields each JPEG as soon as it is complete. Only the newest frame is kept: if the app falls behind, old
/// frames are dropped instead of queued, so the picture stays live.
///
/// URLSession splits the multipart stream itself: every part arrives as a new response followed by its data.
final class MJPEGStream: NSObject, URLSessionDataDelegate, @unchecked Sendable {
    private var buffer = Data()            // delegate queue only
    private var expected: Int64 = -1
    private var emitted = false
    private var continuation: AsyncStream<Data>.Continuation?
    private let rejectedFlag = OSAllocatedUnfairLock(initialState: false)

    /// The server answered, but not with a stream (e.g. 404 from older mission code).
    var rejected: Bool { rejectedFlag.withLock { $0 } }

    func frames(from url: URL) -> AsyncStream<Data> {
        AsyncStream(bufferingPolicy: .bufferingNewest(1)) { continuation in
            self.continuation = continuation
            let config = URLSessionConfiguration.ephemeral
            config.timeoutIntervalForRequest = 4          // the servers send at least one frame a second
            config.timeoutIntervalForResource = 86_400
            config.requestCachePolicy = .reloadIgnoringLocalCacheData
            let queue = OperationQueue()
            queue.maxConcurrentOperationCount = 1
            let session = URLSession(configuration: config, delegate: self, delegateQueue: queue)
            continuation.onTermination = { _ in session.invalidateAndCancel() }
            session.dataTask(with: url).resume()
        }
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive response: URLResponse,
                    completionHandler: @escaping @Sendable (URLSession.ResponseDisposition) -> Void) {
        guard (response as? HTTPURLResponse)?.statusCode == 200 else {
            rejectedFlag.withLock { $0 = true }
            completionHandler(.cancel)
            continuation?.finish()
            return
        }
        buffer.removeAll(keepingCapacity: true)
        expected = response.expectedContentLength
        emitted = false
        completionHandler(.allow)
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        guard !emitted else { return }
        buffer.append(data)
        let complete = expected > 0
            ? Int64(buffer.count) >= expected
            : buffer.count > 4 && buffer[buffer.endIndex - 2] == 0xFF && buffer[buffer.endIndex - 1] == 0xD9
        if complete {
            emitted = true
            continuation?.yield(expected > 0 ? buffer.prefix(Int(expected)) : buffer)
            buffer = Data()
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: (any Error)?) {
        continuation?.finish()
    }
}
