# Changelog

## 1.0.0 (2026-10-14)


### Features

* add a minimum similarity for sources ([69e94c0](https://github.com/shelly-nas/shelly-chat/commit/69e94c075dc54053b753d481df07bc06030d07b4))
* add a settings screen for shared answer and indexing settings ([3db7239](https://github.com/shelly-nas/shelly-chat/commit/3db7239c8eafd0fc29da5e08888f17a872ff3cc9))
* add named indexes with ignore patterns and an editable system prompt ([acba390](https://github.com/shelly-nas/shelly-chat/commit/acba39094355a1e8f2f679a7510397fb429cbc41))
* answer outside the sources, clearly marked ([a0994c5](https://github.com/shelly-nas/shelly-chat/commit/a0994c54df0f67b1e08179626e45174cb6e0e770))
* answer without an index or a working search ([05530b1](https://github.com/shelly-nas/shelly-chat/commit/05530b1e261edbd9a5c3b8a7a398597431965072))
* choose the embedding model under settings ([08421bf](https://github.com/shelly-nas/shelly-chat/commit/08421bff6c895ab8c0f8ee48381a1ba53f8c8234))
* improve search with hybrid keywords, headings and better ranking ([151abad](https://github.com/shelly-nas/shelly-chat/commit/151abad08e9dba36eda3dd6f894065fccbbf84ff))
* index documents from a folder on the NAS instead of GitLab ([e6e47a2](https://github.com/shelly-nas/shelly-chat/commit/e6e47a2de726edb2aa1a27c71f3176402fad4a6a))
* index GitLab sources from an Index screen in the app ([3166c87](https://github.com/shelly-nas/shelly-chat/commit/3166c87ecbc5480bb70a23bf4cae7fdec6a2fad7))
* keep indexing in the background, one run at a time ([7fcaea3](https://github.com/shelly-nas/shelly-chat/commit/7fcaea349a31912788a64b21f24315c69ec2f918))
* let index sources be any path on the NAS ([795c990](https://github.com/shelly-nas/shelly-chat/commit/795c990ebf1cecd82ee5544228d0d90cbe7d22c5))
* scaffold shelly-chat with web and db on the NAS and Ollama on the user's machine ([1d45811](https://github.com/shelly-nas/shelly-chat/commit/1d45811d29f04589eaf2049f66d422b7889be7d2))
* scaffold shelly-chat with web and db on the NAS and Ollama on the user's machine ([7549b19](https://github.com/shelly-nas/shelly-chat/commit/7549b1968a3aaab3ed3f6f37d2dbcee4f0b7e9c5))
* show what an indexing run is doing, and how long each step takes ([e151c38](https://github.com/shelly-nas/shelly-chat/commit/e151c386afc8c5b6ba6ab08ceca2c4d9dde184cb))


### Bug Fixes

* drop sources under 50% relevance by default ([0ca5e10](https://github.com/shelly-nas/shelly-chat/commit/0ca5e1096373b21e57f793c32600a32d26574a27))
* send questions over plain http ([f60d7b6](https://github.com/shelly-nas/shelly-chat/commit/f60d7b64b0902c9ae65486bed15fe1f02d7a2e92))
* stop the indexing progress bar once the run is done ([1a4329a](https://github.com/shelly-nas/shelly-chat/commit/1a4329a54a93c3f3d899ec0bd8ce864d77af0d4f))


### Performance

* keep the language model loaded and show where answer time goes ([3736c9d](https://github.com/shelly-nas/shelly-chat/commit/3736c9d6dd9736cef533ae0fc967842757f172fd))


### Build & Deployment

* check the deploy settings before building for acc ([cd22377](https://github.com/shelly-nas/shelly-chat/commit/cd22377600ae538783f63dc9a5fb9d2faf08c2f3))
