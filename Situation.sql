
USE `agent`;
SET NAMES utf8mb4;

START TRANSACTION;


DELETE FROM `target_ts_sea_point` WHERE `id` BETWEEN 2000 AND 2049;

-- 2026-08-01 08:46:32
-- target_id=3, target_type=cruiser, satellite=卫星A, source_type=0
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2000', 0, '3', 120.268258, 22.683886, '2026-08-01 08:46:32', '2026-08-01 08:46:32', '2026-08-01 08:46:32', '16', 0, '2000', '卫星A', '', 0, '', -1, '', 0.000000, 0.000000);
-- target_id=8, target_type=destroyer, satellite=卫星A, source_type=1
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2001', 1, '8', 120.265593, 22.698244, '2026-08-01 08:46:32', '2026-08-01 08:46:32', '2026-08-01 08:46:32', '16', 0, '2001', '卫星A', '', 0, '', -1, '', 0.000000, 0.000000);
-- target_id=18, target_type=minchuan, satellite=卫星A, source_type=2
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2002', 2, '18', 120.272333, 22.682655, '2026-08-01 08:46:32', '2026-08-01 08:46:32', '2026-08-01 08:46:32', '16', 0, '2002', '卫星A', '', 0, '', -1, '', 0.000000, 0.000000);
-- target_id=24, target_type=minchuan, satellite=卫星A, source_type=0
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2003', 0, '24', 120.274508, 22.695061, '2026-08-01 08:46:32', '2026-08-01 08:46:32', '2026-08-01 08:46:32', '16', 0, '2003', '卫星A', '', 0, '', -1, '', 0.000000, 0.000000);
-- target_id=29, target_type=minchuan, satellite=卫星A, source_type=1
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2004', 1, '29', 120.264438, 22.697204, '2026-08-01 08:46:32', '2026-08-01 08:46:32', '2026-08-01 08:46:32', '16', 0, '2004', '卫星A', '', 0, '', -1, '', 0.000000, 0.000000);

-- 2026-08-02 08:46:32
-- target_id=3, target_type=cruiser, satellite=卫星B, source_type=0
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2005', 0, '3', 120.267073, 22.683917, '2026-08-02 08:46:32', '2026-08-02 08:46:32', '2026-08-02 08:46:32', '17', 0, '2005', '卫星A', '', 0, '', -1, '', 0.001408, 271.62);
-- target_id=8, target_type=destroyer, satellite=卫星B, source_type=1
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2006', 1, '8', 120.265149, 22.697563, '2026-08-02 08:46:32', '2026-08-02 08:46:32', '2026-08-02 08:46:32', '17', 0, '2006', '卫星B', '', 0, '', -1, '', 0.001023, 211.03);
-- target_id=18, target_type=minchuan, satellite=卫星B, source_type=2
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2007', 2, '18', 120.272597, 22.682918, '2026-08-02 08:46:32', '2026-08-02 08:46:32', '2026-08-02 08:46:32', '17', 0, '2007', '卫星B', '', 0, '', -1, '', 0.000461, 42.80);
-- target_id=24, target_type=minchuan, satellite=卫星B, source_type=0
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2008', 0, '24', 120.274169, 22.695248, '2026-08-02 08:46:32', '2026-08-02 08:46:32', '2026-08-02 08:46:32', '17', 0, '2008', '卫星B', '', 0, '', -1, '', 0.000469, 300.88);
-- target_id=29, target_type=minchuan, satellite=卫星B, source_type=1
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2009', 1, '29', 120.264701, 22.697245, '2026-08-02 08:46:32', '2026-08-02 08:46:32', '2026-08-02 08:46:32', '17', 0, '2009', '卫星B', '', 0, '', -1, '', 0.000317, 80.41);

-- 2026-08-03 08:46:32
-- target_id=3, target_type=cruiser, satellite=卫星C, source_type=0
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2010', 0, '3', 120.267317, 22.684220, '2026-08-03 08:46:32', '2026-08-03 08:46:32', '2026-08-03 08:46:32', '18', 0, '2010', '卫星C', '', 0, '', -1, '', 0.000486, 36.61);
-- target_id=8, target_type=destroyer, satellite=卫星C, source_type=1
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2011', 1, '8', 120.264915, 22.697268, '2026-08-03 08:46:32', '2026-08-03 08:46:32', '2026-08-03 08:46:32', '18', 0, '2011', '卫星C', '', 0, '', -1, '', 0.000470, 216.20);
-- target_id=18, target_type=minchuan, satellite=卫星C, source_type=2
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2012', 2, '18', 120.272597, 22.682918, '2026-08-03 08:46:32', '2026-08-03 08:46:32', '2026-08-03 08:46:32', '18', 0, '2012', '卫星C', '', 0, '', -1, '', 0.000000, 42.80);
-- target_id=24, target_type=minchuan, satellite=卫星C, source_type=0
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2013', 0, '24', 120.274169, 22.695248, '2026-08-03 08:46:32', '2026-08-03 08:46:32', '2026-08-03 08:46:32', '18', 0, '2013', '卫星C', '', 0, '', -1, '', 0.000000, 300.88);
-- target_id=29, target_type=minchuan, satellite=卫星C, source_type=1
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2014', 1, '29', 120.264701, 22.697245, '2026-08-03 08:46:32', '2026-08-03 08:46:32', '2026-08-03 08:46:32', '18', 0, '2014', '卫星C', '', 0, '', -1, '', 0.000000, 80.41);

-- 2026-08-04 08:46:32
-- target_id=3, target_type=cruiser, satellite=卫星B, source_type=0
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2015', 0, '3', 120.267459, 22.684975, '2026-08-04 08:46:32', '2026-08-04 08:46:32', '2026-08-04 08:46:32', '19', 0, '2015', '卫星B', '', 0, '', -1, '', 0.000986, 9.84);
-- target_id=8, target_type=destroyer, satellite=卫星B, source_type=1
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2016', 1, '8', 120.265075, 22.697412, '2026-08-04 08:46:32', '2026-08-04 08:46:32', '2026-08-04 08:46:32', '19', 0, '2016', '卫星B', '', 0, '', -1, '', 0.000265, 45.71);
-- target_id=18, target_type=minchuan, satellite=卫星B, source_type=2
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2017', 2, '18', 120.272597, 22.682918, '2026-08-04 08:46:32', '2026-08-04 08:46:32', '2026-08-04 08:46:32', '19', 0, '2017', '卫星B', '', 0, '', -1, '', 0.000000, 42.80);
-- target_id=24, target_type=minchuan, satellite=卫星B, source_type=0
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2018', 0, '24', 120.274169, 22.695248, '2026-08-04 08:46:32', '2026-08-04 08:46:32', '2026-08-04 08:46:32', '19', 0, '2018', '卫星B', '', 0, '', -1, '', 0.000000, 300.88);
-- target_id=29, target_type=minchuan, satellite=卫星B, source_type=1
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2019', 1, '29', 120.264971, 22.697245, '2026-08-04 08:46:32', '2026-08-04 08:46:32', '2026-08-04 08:46:32', '19', 0, '2019', '卫星B', '', 0, '', -1, '', 0.000321, 90.00);

-- 2026-08-05 08:46:32
-- target_id=3, target_type=cruiser, satellite=卫星A, source_type=0
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2020', 0, '3', 120.267385, 22.684597, '2026-08-05 08:46:32', '2026-08-05 08:46:32', '2026-08-05 08:46:32', '20', 0, '2020', '卫星A', '', 0, '', -1, '', 0.000494, 190.24);
-- target_id=8, target_type=destroyer, satellite=卫星A, source_type=1
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2021', 1, '8', 120.265075, 22.697268, '2026-08-05 08:46:32', '2026-08-05 08:46:32', '2026-08-05 08:46:32', '20', 0, '2021', '卫星A', '', 0, '', -1, '', 0.000185, 180.00);
-- target_id=18, target_type=minchuan, satellite=卫星A, source_type=2
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2022', 2, '18', 120.272890, 22.683158, '2026-08-05 08:46:32', '2026-08-05 08:46:32', '2026-08-05 08:46:32', '20', 0, '2022', '卫星A', '', 0, '', -1, '', 0.000465, 48.40);
-- target_id=24, target_type=minchuan, satellite=卫星A, source_type=0
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2023', 0, '24', 120.273889, 22.695512, '2026-08-05 08:46:32', '2026-08-05 08:46:32', '2026-08-05 08:46:32', '20', 0, '2023', '卫星A', '', 0, '', -1, '', 0.000475, 315.62);
-- target_id=29, target_type=minchuan, satellite=卫星A, source_type=1
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2024', 1, '29', 120.264971, 22.697245, '2026-08-05 08:46:32', '2026-08-05 08:46:32', '2026-08-05 08:46:32', '20', 0, '2024', '卫星A', '', 0, '', -1, '', 0.000000, 90.00);

-- 2026-08-06 08:46:32
-- target_id=3, target_type=cruiser, satellite=卫星C, source_type=0
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2025', 0, '3', 120.267383, 22.684597, '2026-08-06 08:46:32', '2026-08-06 08:46:32', '2026-08-06 08:46:32', '21', 0, '2025', '卫星C', '', 0, '', -1, '', 0.000002, 270.00);
-- target_id=8, target_type=destroyer, satellite=卫星C, source_type=1
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2026', 1, '8', 120.264918, 22.697412, '2026-08-06 08:46:32', '2026-08-06 08:46:32', '2026-08-06 08:46:32', '21', 0, '2026', '卫星C', '', 0, '', -1, '', 0.000263, 314.83);
-- target_id=18, target_type=minchuan, satellite=卫星C, source_type=2
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2027', 2, '18', 120.272890, 22.683158, '2026-08-06 08:46:32', '2026-08-06 08:46:32', '2026-08-06 08:46:32', '21', 0, '2027', '卫星C', '', 0, '', -1, '', 0.000000, 48.40);
-- target_id=24, target_type=minchuan, satellite=卫星C, source_type=0
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2028', 0, '24', 120.273889, 22.695512, '2026-08-06 08:46:32', '2026-08-06 08:46:32', '2026-08-06 08:46:32', '21', 0, '2028', '卫星C', '', 0, '', -1, '', 0.000000, 315.62);
-- target_id=29, target_type=minchuan, satellite=卫星C, source_type=1
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2029', 1, '29', 120.265215, 22.697207, '2026-08-06 08:46:32', '2026-08-06 08:46:32', '2026-08-06 08:46:32', '21', 0, '2029', '卫星C', '', 0, '', -1, '', 0.000294, 99.58);

-- 2026-08-07 08:46:32
-- target_id=3, target_type=cruiser, satellite=卫星A, source_type=0
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2030', 0, '3', 120.267455, 22.684975, '2026-08-07 08:46:32', '2026-08-07 08:46:32', '2026-08-07 08:46:32', '22', 0, '2030', '卫星A', '', 0, '', -1, '', 0.000494, 9.97);
-- target_id=8, target_type=destroyer, satellite=卫星A, source_type=1
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2031', 1, '8', 120.265077, 22.697412, '2026-08-07 08:46:32', '2026-08-07 08:46:32', '2026-08-07 08:46:32', '22', 0, '2031', '卫星A', '', 0, '', -1, '', 0.000189, 90.00);
-- target_id=18, target_type=minchuan, satellite=卫星A, source_type=2
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2032', 2, '18', 120.272890, 22.683158, '2026-08-07 08:46:32', '2026-08-07 08:46:32', '2026-08-07 08:46:32', '22', 0, '2032', '卫星A', '', 0, '', -1, '', 0.000000, 48.40);
-- target_id=24, target_type=minchuan, satellite=卫星A, source_type=0
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2033', 0, '24', 120.273889, 22.695512, '2026-08-07 08:46:32', '2026-08-07 08:46:32', '2026-08-07 08:46:32', '22', 0, '2033', '卫星A', '', 0, '', -1, '', 0.000000, 315.62);
-- target_id=29, target_type=minchuan, satellite=卫星A, source_type=1
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2034', 1, '29', 120.265215, 22.697207, '2026-08-07 08:46:32', '2026-08-07 08:46:32', '2026-08-07 08:46:32', '22', 0, '2034', '卫星A', '', 0, '', -1, '', 0.000000, 99.58);

-- 2026-08-08 08:46:32
-- target_id=3, target_type=cruiser, satellite=卫星C, source_type=0
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2035', 0, '3', 120.267308, 22.684220, '2026-08-08 08:46:32', '2026-08-08 08:46:32', '2026-08-08 08:46:32', '23', 0, '2035', '卫星C', '', 0, '', -1, '', 0.000987, 190.18);
-- target_id=8, target_type=destroyer, satellite=卫星C, source_type=1
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2036', 1, '8', 120.264922, 22.697268, '2026-08-08 08:46:32', '2026-08-08 08:46:32', '2026-08-08 08:46:32', '23', 0, '2036', '卫星C', '', 0, '', -1, '', 0.000261, 224.80);
-- target_id=18, target_type=minchuan, satellite=卫星C, source_type=2
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2037', 2, '18', 120.272890, 22.683158, '2026-08-08 08:46:32', '2026-08-08 08:46:32', '2026-08-08 08:46:32', '23', 0, '2037', '卫星C', '', 0, '', -1, '', 0.000000, 48.40);
-- target_id=24, target_type=minchuan, satellite=卫星C, source_type=0
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2038', 0, '24', 120.273889, 22.695512, '2026-08-08 08:46:32', '2026-08-08 08:46:32', '2026-08-08 08:46:32', '23', 0, '2038', '卫星C', '', 0, '', -1, '', 0.000000, 315.62);
-- target_id=29, target_type=minchuan, satellite=卫星C, source_type=1
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2039', 1, '29', 120.265424, 22.697139, '2026-08-08 08:46:32', '2026-08-08 08:46:32', '2026-08-08 08:46:32', '23', 0, '2039', '卫星C', '', 0, '', -1, '', 0.000263, 109.43);

-- 2026-08-09 08:46:32
-- target_id=3, target_type=cruiser, satellite=卫星B, source_type=0
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2040', 0, '3', 120.267378, 22.684597, '2026-08-09 08:46:32', '2026-08-09 08:46:32', '2026-08-09 08:46:32', '24', 0, '2040', '卫星B', '', 0, '', -1, '', 0.000492, 9.72);
-- target_id=8, target_type=destroyer, satellite=卫星B, source_type=1
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2041', 1, '8', 120.264922, 22.697412, '2026-08-09 08:46:32', '2026-08-09 08:46:32', '2026-08-09 08:46:32', '24', 0, '2041', '卫星B', '', 0, '', -1, '', 0.000185, 0.00);
-- target_id=18, target_type=minchuan, satellite=卫星B, source_type=2
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2042', 2, '18', 120.273211, 22.683371, '2026-08-09 08:46:32', '2026-08-09 08:46:32', '2026-08-09 08:46:32', '24', 0, '2042', '卫星B', '', 0, '', -1, '', 0.000470, 54.28);
-- target_id=24, target_type=minchuan, satellite=卫星B, source_type=0
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2043', 0, '24', 120.273689, 22.695836, '2026-08-09 08:46:32', '2026-08-09 08:46:32', '2026-08-09 08:46:32', '24', 0, '2043', '卫星B', '', 0, '', -1, '', 0.000480, 330.34);
-- target_id=29, target_type=minchuan, satellite=卫星B, source_type=1
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2044', 1, '29', 120.265424, 22.697139, '2026-08-09 08:46:32', '2026-08-09 08:46:32', '2026-08-09 08:46:32', '24', 0, '2044', '卫星B', '', 0, '', -1, '', 0.000000, 109.43);

-- 2026-08-10 08:46:32
-- target_id=3, target_type=cruiser, satellite=卫星A, source_type=0
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2045', 0, '3', 120.267376, 22.684597, '2026-08-10 08:46:32', '2026-08-10 08:46:32', '2026-08-10 08:46:32', '25', 0, '2045', '卫星A', '', 0, '', -1, '', 0.000002, 270.00);
-- target_id=8, target_type=destroyer, satellite=卫星A, source_type=1
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2046', 1, '8', 120.265081, 22.697268, '2026-08-10 08:46:32', '2026-08-10 08:46:32', '2026-08-10 08:46:32', '25', 0, '2046', '卫星A', '', 0, '', -1, '', 0.000265, 134.47);
-- target_id=18, target_type=minchuan, satellite=卫星A, source_type=2
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2047', 2, '18', 120.273211, 22.683371, '2026-08-10 08:46:32', '2026-08-10 08:46:32', '2026-08-10 08:46:32', '25', 0, '2047', '卫星A', '', 0, '', -1, '', 0.000000, 54.28);
-- target_id=24, target_type=minchuan, satellite=卫星A, source_type=0
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2048', 0, '24', 120.273689, 22.695836, '2026-08-10 08:46:32', '2026-08-10 08:46:32', '2026-08-10 08:46:32', '25', 0, '2048', '卫星A', '', 0, '', -1, '', 0.000000, 330.34);
-- target_id=29, target_type=minchuan, satellite=卫星A, source_type=1
INSERT INTO `target_ts_sea_point` (`id`, `source_type`, `target_id`, `lng`, `lat`, `target_time`, `create_time`, `update_time`, `ts_id`, `is_realtime`, `record_id`, `satellite_name`, `task_id`, `status`, `image_base_id`, `image_type`, `image_id`, `velocity`, `direction`) VALUES ('2049', 1, '29', 120.265595, 22.697050, '2026-08-10 08:46:32', '2026-08-10 08:46:32', '2026-08-10 08:46:32', '25', 0, '2049', '卫星A', '', 0, '', -1, '', 0.000233, 119.43);

COMMIT;

-- 共50条记录，id和record_id范围：2000-2049。
