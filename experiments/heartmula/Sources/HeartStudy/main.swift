// Two process lifetimes let the language model leave memory before HeartCodec loads.
import Foundation
import HeartMuLaCore
import MLX
import MLXNN
import MLXRandom

struct Request: Decodable {
    let tags: String
    let lyrics: String
    let duration: Double
    let seed: UInt64
}

struct Score: Codable {
    let codes: [Int32]
    let frames: Int
    let endedOnEndToken: Bool
    let seed: UInt64
}

func loadWeights(_ module: Module, at folder: URL, component: String) throws {
    print("Loading \(component) on the CPU")
    var weights = [String: MLXArray]()
    for shard in try WeightIO.shards(in: folder) {
        // Evaluate one lazy file read at a time. A whole-shard eval can trigger
        // a sudden multi-GB allocation while macOS is reclaiming file cache.
        for (key, value) in try loadArrays(url: shard, stream: .cpu).sorted(by: { $0.key < $1.key }) {
            eval(value)
            weights[key] = value
        }
    }
    try WeightIO.apply(weights, to: module, component: component)
    print("Loaded \(component), \(weights.count) tensors")
}

func compose(folder: URL, input: URL, output: URL) throws {
    let request = try JSONDecoder().decode(Request.self, from: Data(contentsOf: input))
    guard (1...120).contains(request.duration) else { throw HeartMuLaError.invalidInput("duration outside 1–120 s") }
    let config = folder.appendingPathComponent("config.json")
    let model = try HeartMuLaModel(ConfigIO.load(HeartMuLaConfig.self, from: config))
    try LMQuantization.from(config: config)?.apply(to: model)
    try loadWeights(model, at: folder, component: "lm")
    let tokenizer = try BPETokenizer(file: folder.appendingPathComponent("tokenizer.json"))
    let gen = try ConfigIO.load(GenConfig.self, from: folder.appendingPathComponent("gen_config.json"))
    let song = SongRequest(tags: request.tags, lyrics: request.lyrics,
                           maxSeconds: SongRequest.lmSeconds(cappingAudioAt: request.duration),
                           seed: request.seed, sampling: SamplingConfig(cfgScale: 1.5))
    let prompt = PromptBuilder.build(tags: song.tags, lyrics: song.lyrics, tokenizer: tokenizer, config: gen)
    guard prompt.length + song.maxFrames <= HeartMuLaPipeline.maxPositions else {
        throw HeartMuLaError.invalidInput("prompt and music exceed context")
    }
    let take = try Rollout.generate(model: model, prompt: prompt, maxMs: song.maxMs,
                                    sampling: song.sampling, noise: MLXNoise(seed: song.seed),
                                    audioEOS: gen.audio_eos_id)
    let score = Score(codes: take.codes.asArray(Int32.self), frames: take.frames,
                      endedOnEndToken: take.endedOnEndToken, seed: song.seed)
    try JSONEncoder().encode(score).write(to: output, options: .atomic)
}

func render(folder: URL, input: URL, output: URL) throws {
    let take = try JSONDecoder().decode(Score.self, from: Data(contentsOf: input))
    guard (1...1500).contains(take.frames), take.codes.count == take.frames * 8,
          take.codes.allSatisfy({ (0..<8192).contains($0) }) else {
        throw HeartMuLaError.invalidInput("invalid HeartCodec frames")
    }
    let codec = HeartCodecModel(try ConfigIO.load(CodecConfig.self, from: folder.appendingPathComponent("config.json")))
    try loadWeights(codec, at: folder, component: "codec")
    MLXRandom.seed(HeartMuLaPipeline.codecSeed(take.seed))
    let frames = MLXArray(take.codes, [8, take.frames])
    let decoded = try Detokenizer.run(codec: codec, codes: frames, steps: 10, guidance: 1.25,
                                      noise: { _, shape in MLXRandom.normal(shape, dtype: .float32) })
    let (audio, peak, gain) = Limiter.apply(decoded.audio)
    guard peak.isFinite, peak > 0 else { throw HeartMuLaError.generation("invalid decoded signal") }
    try WAV.writeFloat32(audio.transposed(1, 0).asArray(Float.self), channels: 2, sampleRate: 48000, to: output)
    print("raw_peak=\(peak) output_gain=\(gain)")
}

setvbuf(stdout, nil, _IOLBF, 0)
let args = CommandLine.arguments
guard args.count == 5 else { fatalError("HeartStudy compose|render model-folder input output") }
Memory.cacheLimit = 128 * 1024 * 1024
let paths = args.dropFirst(2).map { URL(fileURLWithPath: $0) }
switch args[1] {
case "compose": try compose(folder: paths[0], input: paths[1], output: paths[2])
case "render": try render(folder: paths[0], input: paths[1], output: paths[2])
default: throw HeartMuLaError.invalidInput("unknown stage")
}
