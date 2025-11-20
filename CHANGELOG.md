# Changelog

## [1.3.0](https://github.com/cedricziel/ha-sunlit/compare/v1.2.0...v1.3.0) (2025-11-20)


### Features

* support deye 2000 and shelly 3em pro ([#64](https://github.com/cedricziel/ha-sunlit/issues/64)) ([ee3c026](https://github.com/cedricziel/ha-sunlit/commit/ee3c02641819eee64bfbfedb5691347efa2b8b7f))

## [1.2.0](https://github.com/cedricziel/ha-sunlit/compare/v1.1.0...v1.2.0) (2025-09-22)


### Features

* implement sensor groupings with entity categories ([#39](https://github.com/cedricziel/ha-sunlit/issues/39)) ([fd4fdfd](https://github.com/cedricziel/ha-sunlit/commit/fd4fdfdb953330fccf8d52a2775d5d57ffdf4baf))


### Bug Fixes

* battery energy sensors now correctly receive data from MPPT coordinator ([#46](https://github.com/cedricziel/ha-sunlit/issues/46)) ([46eb2e0](https://github.com/cedricziel/ha-sunlit/commit/46eb2e084386d2f342a952496e56a2bb45dbacb0))

## [1.1.0](https://github.com/cedricziel/ha-sunlit/compare/v1.0.0...v1.1.0) (2025-09-13)


### Features

* add SOC event management system ([#34](https://github.com/cedricziel/ha-sunlit/issues/34)) ([b998d00](https://github.com/cedricziel/ha-sunlit/commit/b998d00d75243d256e325ba4ab2bcdaad9678c09))
* implement dynamic discovery of battery extension modules ([#31](https://github.com/cedricziel/ha-sunlit/issues/31)) ([a477007](https://github.com/cedricziel/ha-sunlit/commit/a4770079533b3d6997f865dc1b6839ec1ec3da92))


### Bug Fixes

* ensure total_solar_power uses only inverter power, not battery output ([#36](https://github.com/cedricziel/ha-sunlit/issues/36)) ([ff5fc82](https://github.com/cedricziel/ha-sunlit/commit/ff5fc8238c5e32e06bdb522c9a6fed462b4408d2))
* include battery MPPT power in total solar calculation ([#38](https://github.com/cedricziel/ha-sunlit/issues/38)) ([8a96ae1](https://github.com/cedricziel/ha-sunlit/commit/8a96ae1bf5708b5e67cf13aacd075806a526b63e))

## [1.0.0](https://github.com/cedricziel/ha-sunlit/compare/v0.3.0...v1.0.0) (2025-09-13)


### ⚠ BREAKING CHANGES

* Internal architecture change, no API changes

### Features

* split monolithic coordinator into specialized coordinators ([#28](https://github.com/cedricziel/ha-sunlit/issues/28)) ([a6c719a](https://github.com/cedricziel/ha-sunlit/commit/a6c719aacb4a1fa803bc28f7d4e3daf5114a6b87))

## [0.3.0](https://github.com/cedricziel/ha-sunlit/compare/v0.2.3...v0.3.0) (2025-09-13)


### Features

* add comprehensive testing infrastructure ([1175449](https://github.com/cedricziel/ha-sunlit/commit/11754491d154a7b7e7feda81ecd9547fe906b698))


### Bug Fixes

* correct sensor device class for last_strategy_change ([bcf100e](https://github.com/cedricziel/ha-sunlit/commit/bcf100ed1fc656595dd9dd03cfc2f90b9bdff755))
* cov target ([35645eb](https://github.com/cedricziel/ha-sunlit/commit/35645ebab202c0debd6c3063f269c77c34889b67))
* downgrade pytest-cov to resolve coverage version conflict ([db0c3a5](https://github.com/cedricziel/ha-sunlit/commit/db0c3a56d762b88c7908f239fd7b87ce34aca69a))
* resolve test infrastructure issues with pytest-asyncio compatibility ([b92b8a6](https://github.com/cedricziel/ha-sunlit/commit/b92b8a6c3af258668b68bcc8a5ae93c44e4772e6))
* update dependencies to support pytest-homeassistant-custom-component ([75fe76d](https://github.com/cedricziel/ha-sunlit/commit/75fe76d6c9edaee7740a26b3f76447d2c82a72da))
* upgrade pytest-homeassistant-custom-component==0.13.278 ([5ea7e35](https://github.com/cedricziel/ha-sunlit/commit/5ea7e35c5232cd3854fdfd71cdbc4d642c77c795))

## [0.2.3](https://github.com/cedricziel/ha-sunlit/compare/v0.2.2...v0.2.3) (2025-09-10)


### Bug Fixes

* uninitialized variable ([d109745](https://github.com/cedricziel/ha-sunlit/commit/d109745481f4fe8010cae091832f04f389bebf00))

## [0.2.2](https://github.com/cedricziel/ha-sunlit/compare/v0.2.1...v0.2.2) (2025-09-10)


### Bug Fixes

* add aiohttp to dependencies ([1aee98c](https://github.com/cedricziel/ha-sunlit/commit/1aee98cddcd88a0a5f9f8e0aab466d108cb0c93b))

## [0.2.1](https://github.com/cedricziel/ha-sunlit/compare/v0.2.0...v0.2.1) (2025-09-10)


### Bug Fixes

* bring back manifest ([865878c](https://github.com/cedricziel/ha-sunlit/commit/865878cf5c768e39b3dbfcd7633d8abc85c22585))
* bump python version to 3.13 ([2c9e0a8](https://github.com/cedricziel/ha-sunlit/commit/2c9e0a8a786f522810fe124d4b11289f210fd3b5))

## [0.2.0](https://github.com/cedricziel/ha-sunlit/compare/v0.1.0...v0.2.0) (2025-09-10)


### Features

* add charging box strategy endpoint support ([7eb0670](https://github.com/cedricziel/ha-sunlit/commit/7eb0670676742ada8d4c8b1a71ababcfc32d189f))
* add comprehensive debug logging for troubleshooting ([3e15462](https://github.com/cedricziel/ha-sunlit/commit/3e154624342e28ab7b5993f875e64c071106f409))
* add support for new device types ([34bf5b7](https://github.com/cedricziel/ha-sunlit/commit/34bf5b7c967d1ce83f9daffad7621427728a27d0))


### Bug Fixes

* correct debug config ([e053cb1](https://github.com/cedricziel/ha-sunlit/commit/e053cb13504582d8f11eee5d0b0a0bc5677d4f2e))
* remove release job ([5f90c8f](https://github.com/cedricziel/ha-sunlit/commit/5f90c8f586666bcce9d2120ee91d60298662ff74))

## [0.1.0](https://github.com/cedricziel/ha-sunlit/compare/v0.0.1...v0.1.0) (2025-09-07)


### Features

* add battery IO power statistics endpoint ([924db0a](https://github.com/cedricziel/ha-sunlit/commit/924db0ab94a31710b8703a4d8b4402b7c12eb63b))
* add device details endpoint to API client ([f1761fe](https://github.com/cedricziel/ha-sunlit/commit/f1761fe4564e955a866f89731c18c0dfb98d810b))
* add device list endpoint to API client ([120d2e3](https://github.com/cedricziel/ha-sunlit/commit/120d2e38b354389add8f97a3e22275619a756d62))
* add device statistics endpoint to API client ([7303883](https://github.com/cedricziel/ha-sunlit/commit/73038831a341d4657741ed9f0c7c595858df91ec))
* add grid export energy tracking sensors ([115c7e1](https://github.com/cedricziel/ha-sunlit/commit/115c7e10e77e421f150af540aa42b9e79ea301c7))
* add multi-family support with hardcoded Sunlit API ([2cae349](https://github.com/cedricziel/ha-sunlit/commit/2cae349b538ef32a19b309ef3c2c482d1b1ab237))
* add space SOC and strategy endpoints for battery management ([ca267ed](https://github.com/cedricziel/ha-sunlit/commit/ca267ed09d5930a72d5db76736cff9e24afef457))
* add strategy history endpoint with limited backfill support ([da56a3a](https://github.com/cedricziel/ha-sunlit/commit/da56a3a623bd75b9a4990112d4521bbdb3fd0b6f))
* add Sunlit REST integration for HomeAssistant ([34b7104](https://github.com/cedricziel/ha-sunlit/commit/34b7104922e6be9b395df5f7b5878c0067be48c2))
* add support for unassigned devices without spaceId ([6961456](https://github.com/cedricziel/ha-sunlit/commit/69614560fb473bb4aceed45a433280e7c0bc74e3))
* add virtual devices for battery modules ([aba78bf](https://github.com/cedricziel/ha-sunlit/commit/aba78bf9ad536409055772e69f119ed0c481457a))
* enable Energy Dashboard integration for solar and grid monitoring ([bc4e2f9](https://github.com/cedricziel/ha-sunlit/commit/bc4e2f9a62f036d0e62cbe53d635ba75cd4eb7ff))
* enhance device info with actual API response data ([ddb3aa5](https://github.com/cedricziel/ha-sunlit/commit/ddb3aa5531a62bef7b8b70e8d5658c89423c5a60))
* fetch statistics for all online devices and add inverter total yield ([779de90](https://github.com/cedricziel/ha-sunlit/commit/779de90be18c7c9a328b649cd3c909ee6181ea4b))
* implement consistent sensor naming with sunlit prefix and friendly names ([c03cc3c](https://github.com/cedricziel/ha-sunlit/commit/c03cc3cf2eef83e0172180abec0a4b5fd6252596))
* implement email/password authentication ([8f12542](https://github.com/cedricziel/ha-sunlit/commit/8f12542d4fabd9ac8e3129adb5d1ff15984bbb4a))
* improve device attributes and add battery capacity sensors ([75049cf](https://github.com/cedricziel/ha-sunlit/commit/75049cfc4b3aa62d87d18e98578cd1f649fa17ad))
* integrate v1.5 space/index endpoint for efficient data fetching ([0b80b4e](https://github.com/cedricziel/ha-sunlit/commit/0b80b4e85e195ae14975db57a9289a68147c8a16))
* restructure entities to use appropriate platform types ([0c95259](https://github.com/cedricziel/ha-sunlit/commit/0c952597102a2cd017e135d6914ec7828d54c76b))


### Bug Fixes

* battery_full sensor should not have battery device class ([35df805](https://github.com/cedricziel/ha-sunlit/commit/35df8052f1f19015b9d0ff020983d53ca3a79442))
* correct device and state classes for sensors ([bbc2cc3](https://github.com/cedricziel/ha-sunlit/commit/bbc2cc31244252f328be079bc78064f152ffbbc3))
* correct device class assignment for current_power sensor ([3ab4f4d](https://github.com/cedricziel/ha-sunlit/commit/3ab4f4d49d8bf4c3ca438bf133982c350c599aff))
* correct device list API response structure ([4b3585c](https://github.com/cedricziel/ha-sunlit/commit/4b3585ce38e5ce9933d8a81622efa7de9f494cf0))
* correct OpenAPI schema structure based on actual API responses ([9f59300](https://github.com/cedricziel/ha-sunlit/commit/9f5930072d27c3884af009a85141a0cab8c87d4f))
* correct unit assignment for current_power sensor ([b5a9abc](https://github.com/cedricziel/ha-sunlit/commit/b5a9abc508fc117edba7ea72b67c606eae7194b3))
* hassfest ([5ac615b](https://github.com/cedricziel/ha-sunlit/commit/5ac615b55a51d3905c60aeea7e01400d7e37f30f))
* improve battery module sensor handling for incomplete data ([8c9032a](https://github.com/cedricziel/ha-sunlit/commit/8c9032a235f32394b8702177f965712e9e3aac3d))
* improve sensor configuration and add icons ([89c4b75](https://github.com/cedricziel/ha-sunlit/commit/89c4b75256d2e9ded9177a895d1c65ab50d39a52))
* resolve device ID type mismatch preventing device creation ([35dc521](https://github.com/cedricziel/ha-sunlit/commit/35dc521dc69d5379f5b26535ec4ec40fa0223abf))
* revert device_type parameter to "ALL" to fix API error ([9c49326](https://github.com/cedricziel/ha-sunlit/commit/9c493263823572d1a3290846c4842f435a26a518))
* revert select entities back to text sensors ([66974e4](https://github.com/cedricziel/ha-sunlit/commit/66974e40917df38dd750674576700d618ce6b525))
* update coordinator and implement device mapping ([561f392](https://github.com/cedricziel/ha-sunlit/commit/561f3926a2d1ff46fd1123f485fc1da21d49f5db))
* update device statistics response and migrate to OpenAPI 3.1.0 nullable syntax ([a2529ca](https://github.com/cedricziel/ha-sunlit/commit/a2529ca91b6d99f3d3e9ec32f0a13c80a1d3f619))
* use friendly names for sensor entity names ([2f0d4c8](https://github.com/cedricziel/ha-sunlit/commit/2f0d4c8c7cbd4f1c6da30beb41b48f99a7d37aa1))
* use line-marker ([8f559e5](https://github.com/cedricziel/ha-sunlit/commit/8f559e50c76d52f93c55d15cccd1e0244cfd0562))
* use line-marker ([b75eb0d](https://github.com/cedricziel/ha-sunlit/commit/b75eb0d86fdfaa027c4f3c5a4038955a6216745c))
