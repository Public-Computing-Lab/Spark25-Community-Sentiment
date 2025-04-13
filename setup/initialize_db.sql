# Created: April 9, 2025 
# Encoding: Unicode (UTF-8)

SET @ORIG_FOREIGN_KEY_CHECKS = @@FOREIGN_KEY_CHECKS;
SET FOREIGN_KEY_CHECKS = 0;

SET @ORIG_UNIQUE_CHECKS = @@UNIQUE_CHECKS;
SET UNIQUE_CHECKS = 0;

SET @ORIG_TIME_ZONE = @@TIME_ZONE;
SET TIME_ZONE = '+00:00';

DROP DATABASE IF EXISTS `rethink_ai_boston`
CREATE DATABASE IF NOT EXISTS `rethink_ai_boston` DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_general_ci;
USE `rethink_ai_boston`;

DROP TABLE IF EXISTS `zipcode_geo`;
DROP TABLE IF EXISTS `shots_fired_data`;
DROP TABLE IF EXISTS `llm_summaries`;
DROP TABLE IF EXISTS `interaction_log`;
DROP TABLE IF EXISTS `homicide_data`;
DROP TABLE IF EXISTS `bos311_data`;
DROP TABLE IF EXISTS `boston_census_2020`;

CREATE TABLE `bos311_data` (
  `id` int NOT NULL AUTO_INCREMENT,
  `case_enquiry_id` bigint DEFAULT NULL,
  `open_dt` datetime DEFAULT NULL,
  `sla_target_dt` datetime DEFAULT NULL,
  `closed_dt` datetime DEFAULT NULL,
  `on_time` varchar(20) DEFAULT NULL,
  `case_status` varchar(50) DEFAULT NULL,
  `closure_reason` text,
  `case_title` varchar(255) DEFAULT NULL,
  `subject` varchar(100) DEFAULT NULL,
  `reason` varchar(100) DEFAULT NULL,
  `type` varchar(100) DEFAULT NULL,
  `queue` varchar(100) DEFAULT NULL,
  `department` varchar(100) DEFAULT NULL,
  `submitted_photo` varchar(255) DEFAULT NULL,
  `closed_photo` varchar(255) DEFAULT NULL,
  `location` varchar(255) DEFAULT NULL,
  `fire_district` varchar(10) DEFAULT NULL,
  `pwd_district` varchar(10) DEFAULT NULL,
  `city_council_district` varchar(10) DEFAULT NULL,
  `police_district` varchar(20) DEFAULT NULL,
  `neighborhood` varchar(100) DEFAULT NULL,
  `neighborhood_services_district` varchar(10) DEFAULT NULL,
  `ward` varchar(20) DEFAULT NULL,
  `precinct` varchar(20) DEFAULT NULL,
  `location_street_name` varchar(255) DEFAULT NULL,
  `location_zipcode` varchar(10) DEFAULT NULL,
  `census_block_geo_id` bigint DEFAULT NULL,
  `latitude` decimal(18,14) DEFAULT NULL,
  `longitude` decimal(18,14) DEFAULT NULL,
  `geom_4326` varchar(100) DEFAULT NULL,
  `source` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_bos311_filter` (`neighborhood`,`police_district`,`type`,`open_dt`)
) ENGINE=InnoDB AUTO_INCREMENT=1872650 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `homicide_data` (
  `id` int NOT NULL AUTO_INCREMENT,
  `object_id` int DEFAULT NULL,
  `reporting_event_number` varchar(20) DEFAULT NULL,
  `ruled_date` datetime DEFAULT NULL,
  `homicide_date` datetime DEFAULT NULL,
  `district` varchar(10) DEFAULT NULL,
  `victim_age` int DEFAULT NULL,
  `race` varchar(50) DEFAULT NULL,
  `gender` varchar(10) DEFAULT NULL,
  `weapon` varchar(20) DEFAULT NULL,
  `hour_of_day` int DEFAULT NULL,
  `day_of_week` int DEFAULT NULL,
  `year` int DEFAULT NULL,
  `quarter` int DEFAULT NULL,
  `month` int DEFAULT NULL,
  `neighborhood` varchar(50) DEFAULT NULL,
  `ethnicity_nibrs` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_homicide_filter` (`neighborhood`,`district`,`year`,`homicide_date`)
) ENGINE=InnoDB AUTO_INCREMENT=426 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `interaction_log` (
  `id` int NOT NULL AUTO_INCREMENT,
  `session_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `app_version` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `data_selected` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `data_attributes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `client_response_rating` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `prompt_preamble` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `client_query` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `app_response` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4426 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `llm_summaries` (
  `id` int NOT NULL AUTO_INCREMENT,
  `month_label` varchar(7) NOT NULL,
  `summary` text NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_month` (`month_label`)
) ENGINE=InnoDB AUTO_INCREMENT=85 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `shots_fired_data` (
  `id` int NOT NULL AUTO_INCREMENT,
  `object_id` int DEFAULT NULL,
  `incident_num` varchar(20) DEFAULT NULL,
  `incident_date` bigint DEFAULT NULL,
  `incident_date_time` datetime DEFAULT NULL,
  `address` varchar(255) DEFAULT NULL,
  `district` varchar(10) DEFAULT NULL,
  `ballistics_evidence` int DEFAULT NULL,
  `latitude` decimal(10,8) DEFAULT NULL,
  `longitude` decimal(10,8) DEFAULT NULL,
  `census_block_geo_id` bigint DEFAULT NULL,
  `hour_of_day` int DEFAULT NULL,
  `day_of_week` int DEFAULT NULL,
  `year` int DEFAULT NULL,
  `quarter` int DEFAULT NULL,
  `month` int DEFAULT NULL,
  `neighborhood` varchar(20) DEFAULT NULL,
  `geometry_x` decimal(10,8) DEFAULT NULL,
  `geometry_y` decimal(10,8) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_shots_filter` (`neighborhood`,`district`,`year`,`incident_date_time`)
) ENGINE=InnoDB AUTO_INCREMENT=8771 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


CREATE TABLE `zipcode_geo` (
  `zipcode` varchar(10) NOT NULL,
  `boundary` geometry DEFAULT NULL,
  PRIMARY KEY (`zipcode`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `boston_census_2020` (
  `geo_id` bigint NOT NULL,
  `block_area_name` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `race_total` int DEFAULT NULL,
  `one_race_total` int DEFAULT NULL,
  `race_white` int DEFAULT NULL,
  `race_black` int DEFAULT NULL,
  `race_native` int DEFAULT NULL,
  `race_asian` int DEFAULT NULL,
  `race_pacific_islander` int DEFAULT NULL,
  `race_other` int DEFAULT NULL,
  `two_race_total` int DEFAULT NULL,
  `race_white_black` int DEFAULT NULL,
  `race_white_native` int DEFAULT NULL,
  `race_white_asian` int DEFAULT NULL,
  `race_white_pacific_islander` int DEFAULT NULL,
  `race_white_other` int DEFAULT NULL,
  `race_black_native` int DEFAULT NULL,
  `race_black_asian` int DEFAULT NULL,
  `race_black_pacific_islander` int DEFAULT NULL,
  `race_black_other` int DEFAULT NULL,
  `race_native_asian` int DEFAULT NULL,
  `race_native_pacific_islander` int DEFAULT NULL,
  `race_native_other` int DEFAULT NULL,
  `race_asian_pacific_islander` int DEFAULT NULL,
  `race_asian_other` int DEFAULT NULL,
  `race_pacific_islander_other` int DEFAULT NULL,
  `three_race_total` int DEFAULT NULL,
  `race_white_black_native` int DEFAULT NULL,
  `race_white_black_asian` int DEFAULT NULL,
  `race_white_black_pacific_islander` int DEFAULT NULL,
  `race_white_black_other` int DEFAULT NULL,
  `race_white_native_asian` int DEFAULT NULL,
  `race_white_native_pacific_islander` int DEFAULT NULL,
  `race_white_native_other` int DEFAULT NULL,
  `race_white_asian_native` int DEFAULT NULL,
  `race_white_asian_other` int DEFAULT NULL,
  `race_white_pacific_islander_other` int DEFAULT NULL,
  `race_black_native_asian` int DEFAULT NULL,
  `race_black_native_pacific_islander` int DEFAULT NULL,
  `race_black_native_other` int DEFAULT NULL,
  `race_black_asian_pacific_islander` int DEFAULT NULL,
  `race_black_asian_other` int DEFAULT NULL,
  `race_black_pacific_islander_other` int DEFAULT NULL,
  `race_native_asian_pacific_islander` int DEFAULT NULL,
  `race_native_asian_other` int DEFAULT NULL,
  `race_native_pacific_islander_other` int DEFAULT NULL,
  `race_asian_pacific_islander_other` int DEFAULT NULL,
  `four_race_total` int DEFAULT NULL,
  `five_race_total` int DEFAULT NULL,
  `six_race_total` int DEFAULT NULL,
  `sex_age_total` int DEFAULT NULL,
  `male_total` int DEFAULT NULL,
  `male_under_5` int DEFAULT NULL,
  `male_5_to_9` int DEFAULT NULL,
  `male_10_to_14` int DEFAULT NULL,
  `male_15_to_17` int DEFAULT NULL,
  `male_18_to_19` int DEFAULT NULL,
  `male_20` int DEFAULT NULL,
  `male_21` int DEFAULT NULL,
  `male_22_to_24` int DEFAULT NULL,
  `male_25_to_29` int DEFAULT NULL,
  `male_30_to_34` int DEFAULT NULL,
  `male_35_to_39` int DEFAULT NULL,
  `male_40_to_44` int DEFAULT NULL,
  `male_45_to_49` int DEFAULT NULL,
  `male_50_to_54` int DEFAULT NULL,
  `male_55_to_59` int DEFAULT NULL,
  `male_60_to_61` int DEFAULT NULL,
  `male_62_to_64` int DEFAULT NULL,
  `male_65_to_66` int DEFAULT NULL,
  `male_67_to_69` int DEFAULT NULL,
  `male_70_to_74` int DEFAULT NULL,
  `male_75_to_79` int DEFAULT NULL,
  `male_80_to_84` int DEFAULT NULL,
  `male_85_plus` int DEFAULT NULL,
  `female_total` int DEFAULT NULL,
  `female_under_5` int DEFAULT NULL,
  `female_5_to_9` int DEFAULT NULL,
  `female_10_to_14` int DEFAULT NULL,
  `female_15_to_17` int DEFAULT NULL,
  `female_18_to_19` int DEFAULT NULL,
  `female_20` int DEFAULT NULL,
  `female_21` int DEFAULT NULL,
  `female_22_to_24` int DEFAULT NULL,
  `female_25_to_29` int DEFAULT NULL,
  `female_30_to_34` int DEFAULT NULL,
  `female_35_to_39` int DEFAULT NULL,
  `female_40_to_44` int DEFAULT NULL,
  `female_45_to_49` int DEFAULT NULL,
  `female_50_to_54` int DEFAULT NULL,
  `female_55_to_59` int DEFAULT NULL,
  `female_60_to_61` int DEFAULT NULL,
  `female_62_to_64` int DEFAULT NULL,
  `female_65_to_66` int DEFAULT NULL,
  `female_67_to_69` int DEFAULT NULL,
  `female_70_to_74` int DEFAULT NULL,
  `female_75_to_79` int DEFAULT NULL,
  `female_80_to_84` int DEFAULT NULL,
  `female_85_plus` int DEFAULT NULL,
  `housing_total` int DEFAULT NULL,
  `housing_total_owner_occupied` int DEFAULT NULL,
  `owner_occupied_15_to_24` int DEFAULT NULL,
  `owner_occupied_25_to_34` int DEFAULT NULL,
  `owner_occupied_35_to_44` int DEFAULT NULL,
  `owner_occupied_45_to_54` int DEFAULT NULL,
  `owner_occupied_55_to_59` int DEFAULT NULL,
  `owner_occupied_60_to_64` int DEFAULT NULL,
  `owner_occupied_65_to_74` int DEFAULT NULL,
  `owner_occupied_75_to_84` int DEFAULT NULL,
  `owner_occupied_85_plus` int DEFAULT NULL,
  `housing_total_renter_occupied` int DEFAULT NULL,
  `renter_occupied_15_to_24` int DEFAULT NULL,
  `renter_occupied_25_to_34` int DEFAULT NULL,
  `renter_occupied_35_to_44` int DEFAULT NULL,
  `renter_occupied_45_to_54` int DEFAULT NULL,
  `renter_occupied_55_to_59` int DEFAULT NULL,
  `renter_occupied_60_to_64` int DEFAULT NULL,
  `renter_occupied_65_to_74` int DEFAULT NULL,
  `renter_occupied_75_to_84` int DEFAULT NULL,
  `renter_occupied_85_plus` int DEFAULT NULL,
  PRIMARY KEY (`geo_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;





SET FOREIGN_KEY_CHECKS = @ORIG_FOREIGN_KEY_CHECKS;

SET UNIQUE_CHECKS = @ORIG_UNIQUE_CHECKS;

SET @ORIG_TIME_ZONE = @@TIME_ZONE;
SET TIME_ZONE = @ORIG_TIME_ZONE;
