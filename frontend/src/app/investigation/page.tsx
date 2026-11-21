import { Suspense } from "react";

import { Investigation } from "@/components/investigation";
import { Loading } from "@/components/ui";

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <Investigation />
    </Suspense>
  );
}
