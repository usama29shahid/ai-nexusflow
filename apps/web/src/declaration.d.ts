import {
    ApexForecastDataPoints as ApexForecastDataPointsType,
    type ApexGrid as ApexGridType,
    type ApexStroke as ApexStrokeType,
} from "apexcharts";
import "apexcharts";
import type { CalendarDateProps, CalendarMonthProps, CalendarMultiProps, CalendarRangeProps } from "cally";

declare module "filepond-plugin-image-preview";

declare module "apexcharts" {
    type ApexGrid = ApexGridType & {
        strokeDashArray?: number | number[];
    };

    type ApexStroke = ApexStrokeType & {
        dashArray: number | number[];
    };

    type ApexForecastDataPoints = ApexForecastDataPointsType & {
        dashArray: number | number[];
    };
}

declare module "react" {
    interface CSSProperties {
        "anchor-name"?: string;
        anchorName?: string;
        positionAnchor?: string;
        "position-anchor"?: string;
        "--value"?: string | number;
        "--thickness"?: string | number;
        "--size"?: string | number;
    }
    namespace JSX {
        interface IntrinsicElements {
            "calendar-month": CalendarMonthProps &
                HTMLAttributes<HTMLElement> & { onchange?: FormEventHandler<HTMLInputElement> };
            "calendar-range": CalendarRangeProps &
                HTMLAttributes<HTMLElement> & { onchange?: FormEventHandler<HTMLInputElement> };
            "calendar-date": CalendarDateProps &
                HTMLAttributes<HTMLElement> & { onchange?: FormEventHandler<HTMLInputElement> };
            "calendar-multi": CalendarMultiProps &
                HTMLAttributes<HTMLElement> & { onchange?: FormEventHandler<HTMLInputElement> };
        }
    }
}

declare module "react-apexcharts" {
    interface Props {
        type?: NonNullable<ApexOptions["chart"]>["type"];
    }
}
