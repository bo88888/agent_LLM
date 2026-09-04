-- 最新态势轨迹融合数据
-- 来源：Situation(2).sql
-- 用途：替换联网机MySQL中旧的target_situation_track数据
-- 目标：3=cruiser，8=destroyer，18/24/29=minchuan
-- 共5个目标、50个轨迹点；经纬度和时间完全继承Situation(2).sql

USE `agent`;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `target_situation_track` (
  `target_id` BIGINT UNSIGNED NOT NULL COMMENT '态势目标ID',
  `target_type` VARCHAR(64) NOT NULL COMMENT '目标类型',
  `lng` DOUBLE NOT NULL COMMENT 'WGS84经度',
  `lat` DOUBLE NOT NULL COMMENT 'WGS84纬度',
  `target_time` DATETIME NOT NULL COMMENT '态势点时间',
  PRIMARY KEY (`target_id`, `target_time`),
  INDEX `idx_situation_lng_lat` (`lng`, `lat`),
  INDEX `idx_situation_time` (`target_time`),
  INDEX `idx_situation_type_time` (`target_type`, `target_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

START TRANSACTION;

-- 删除旧态势轨迹；不影响target_prior先验表。
DELETE FROM `target_situation_track`;

-- target_id=3, target_type=cruiser, 最新匹配点=(120.267376, 22.684597)
INSERT INTO `target_situation_track` (`target_id`, `target_type`, `lng`, `lat`, `target_time`) VALUES
  (3, 'cruiser', 120.268258, 22.683886, '2026-08-01 08:46:32'),
  (3, 'cruiser', 120.267073, 22.683917, '2026-08-02 08:46:32'),
  (3, 'cruiser', 120.267317, 22.684220, '2026-08-03 08:46:32'),
  (3, 'cruiser', 120.267459, 22.684975, '2026-08-04 08:46:32'),
  (3, 'cruiser', 120.267385, 22.684597, '2026-08-05 08:46:32'),
  (3, 'cruiser', 120.267383, 22.684597, '2026-08-06 08:46:32'),
  (3, 'cruiser', 120.267455, 22.684975, '2026-08-07 08:46:32'),
  (3, 'cruiser', 120.267308, 22.684220, '2026-08-08 08:46:32'),
  (3, 'cruiser', 120.267378, 22.684597, '2026-08-09 08:46:32'),
  (3, 'cruiser', 120.267376, 22.684597, '2026-08-10 08:46:32')
ON DUPLICATE KEY UPDATE `target_type`=VALUES(`target_type`), `lng`=VALUES(`lng`), `lat`=VALUES(`lat`);

-- target_id=8, target_type=destroyer, 最新匹配点=(120.265081, 22.697268)
INSERT INTO `target_situation_track` (`target_id`, `target_type`, `lng`, `lat`, `target_time`) VALUES
  (8, 'destroyer', 120.265593, 22.698244, '2026-08-01 08:46:32'),
  (8, 'destroyer', 120.265149, 22.697563, '2026-08-02 08:46:32'),
  (8, 'destroyer', 120.264915, 22.697268, '2026-08-03 08:46:32'),
  (8, 'destroyer', 120.265075, 22.697412, '2026-08-04 08:46:32'),
  (8, 'destroyer', 120.265075, 22.697268, '2026-08-05 08:46:32'),
  (8, 'destroyer', 120.264918, 22.697412, '2026-08-06 08:46:32'),
  (8, 'destroyer', 120.265077, 22.697412, '2026-08-07 08:46:32'),
  (8, 'destroyer', 120.264922, 22.697268, '2026-08-08 08:46:32'),
  (8, 'destroyer', 120.264922, 22.697412, '2026-08-09 08:46:32'),
  (8, 'destroyer', 120.265081, 22.697268, '2026-08-10 08:46:32')
ON DUPLICATE KEY UPDATE `target_type`=VALUES(`target_type`), `lng`=VALUES(`lng`), `lat`=VALUES(`lat`);

-- target_id=18, target_type=minchuan, 最新匹配点=(120.273211, 22.683371)
INSERT INTO `target_situation_track` (`target_id`, `target_type`, `lng`, `lat`, `target_time`) VALUES
  (18, 'minchuan', 120.272333, 22.682655, '2026-08-01 08:46:32'),
  (18, 'minchuan', 120.272597, 22.682918, '2026-08-02 08:46:32'),
  (18, 'minchuan', 120.272597, 22.682918, '2026-08-03 08:46:32'),
  (18, 'minchuan', 120.272597, 22.682918, '2026-08-04 08:46:32'),
  (18, 'minchuan', 120.272890, 22.683158, '2026-08-05 08:46:32'),
  (18, 'minchuan', 120.272890, 22.683158, '2026-08-06 08:46:32'),
  (18, 'minchuan', 120.272890, 22.683158, '2026-08-07 08:46:32'),
  (18, 'minchuan', 120.272890, 22.683158, '2026-08-08 08:46:32'),
  (18, 'minchuan', 120.273211, 22.683371, '2026-08-09 08:46:32'),
  (18, 'minchuan', 120.273211, 22.683371, '2026-08-10 08:46:32')
ON DUPLICATE KEY UPDATE `target_type`=VALUES(`target_type`), `lng`=VALUES(`lng`), `lat`=VALUES(`lat`);

-- target_id=24, target_type=minchuan, 最新匹配点=(120.273689, 22.695836)
INSERT INTO `target_situation_track` (`target_id`, `target_type`, `lng`, `lat`, `target_time`) VALUES
  (24, 'minchuan', 120.274508, 22.695061, '2026-08-01 08:46:32'),
  (24, 'minchuan', 120.274169, 22.695248, '2026-08-02 08:46:32'),
  (24, 'minchuan', 120.274169, 22.695248, '2026-08-03 08:46:32'),
  (24, 'minchuan', 120.274169, 22.695248, '2026-08-04 08:46:32'),
  (24, 'minchuan', 120.273889, 22.695512, '2026-08-05 08:46:32'),
  (24, 'minchuan', 120.273889, 22.695512, '2026-08-06 08:46:32'),
  (24, 'minchuan', 120.273889, 22.695512, '2026-08-07 08:46:32'),
  (24, 'minchuan', 120.273889, 22.695512, '2026-08-08 08:46:32'),
  (24, 'minchuan', 120.273689, 22.695836, '2026-08-09 08:46:32'),
  (24, 'minchuan', 120.273689, 22.695836, '2026-08-10 08:46:32')
ON DUPLICATE KEY UPDATE `target_type`=VALUES(`target_type`), `lng`=VALUES(`lng`), `lat`=VALUES(`lat`);

-- target_id=29, target_type=minchuan, 最新匹配点=(120.265595, 22.697050)
INSERT INTO `target_situation_track` (`target_id`, `target_type`, `lng`, `lat`, `target_time`) VALUES
  (29, 'minchuan', 120.264438, 22.697204, '2026-08-01 08:46:32'),
  (29, 'minchuan', 120.264701, 22.697245, '2026-08-02 08:46:32'),
  (29, 'minchuan', 120.264701, 22.697245, '2026-08-03 08:46:32'),
  (29, 'minchuan', 120.264971, 22.697245, '2026-08-04 08:46:32'),
  (29, 'minchuan', 120.264971, 22.697245, '2026-08-05 08:46:32'),
  (29, 'minchuan', 120.265215, 22.697207, '2026-08-06 08:46:32'),
  (29, 'minchuan', 120.265215, 22.697207, '2026-08-07 08:46:32'),
  (29, 'minchuan', 120.265424, 22.697139, '2026-08-08 08:46:32'),
  (29, 'minchuan', 120.265424, 22.697139, '2026-08-09 08:46:32'),
  (29, 'minchuan', 120.265595, 22.697050, '2026-08-10 08:46:32')
ON DUPLICATE KEY UPDATE `target_type`=VALUES(`target_type`), `lng`=VALUES(`lng`), `lat`=VALUES(`lat`);

COMMIT;

-- 已写入50条最新态势轨迹。
